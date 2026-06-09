"""Service runtime orchestration with daemon lifecycle and persistent logs."""

import asyncio
import json
import os
import shlex
import signal
import socket
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from session_forge.config import Config, config
from session_forge.paths import logs_dir, service_ports_path


_STATE_LOCK = threading.Lock()
_MANAGED_SERVICES = ("proxy", "mcp_server", "llama")


@dataclass
class ServiceSpec:
    name: str
    host: str
    preferred_port: int
    range_start: int
    range_end: int
    health_path: str
    expected_service_marker: str | None
    start_cmd: str
    cmd_signature: str


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ts_compact() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.localtime())


def _normalize_range(start: int, end: int) -> tuple[int, int]:
    if end < start:
        return end, start
    return start, end


def _candidate_ports(preferred: int, start: int, end: int) -> list[int]:
    start, end = _normalize_range(start, end)
    ports = [preferred]
    ports.extend(p for p in range(start, end + 1) if p != preferred)
    return ports


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _pid_for_port(port: int) -> int | None:
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return None
    if not out:
        return None
    line = out.splitlines()[0].strip()
    return int(line) if line.isdigit() else None


def _cmdline_for_pid(pid: int) -> str:
    try:
        out = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "command="],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:
        return ""
    return out.strip()


def _cmd_matches_signature(cmdline: str, signature: str) -> bool:
    if not cmdline:
        return False
    return signature.lower() in cmdline.lower()


def _port_in_use(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False


def _read_state_raw() -> dict[str, dict]:
    path = service_ports_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state_raw(data: dict[str, dict]) -> None:
    path = service_ports_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
    ) as tmp:
        json.dump(data, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def read_service_state() -> dict[str, dict]:
    with _STATE_LOCK:
        return _read_state_raw()


def _upsert_state(service: str, record: dict) -> None:
    with _STATE_LOCK:
        data = _read_state_raw()
        data[service] = record
        _write_state_raw(data)


def _remove_state(service: str) -> None:
    with _STATE_LOCK:
        data = _read_state_raw()
        data.pop(service, None)
        _write_state_raw(data)


def _url_host_port(url: str, default_port: int) -> tuple[str, int]:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or default_port
    return host, port


def _configured_port(service: str, cfg: Config) -> int:
    if service == "proxy":
        return cfg.proxy.port
    if service == "mcp_server":
        return cfg.mcp_server.port
    if service == "llama":
        _, port = _url_host_port(cfg.llama.server_url, 8080)
        return port
    raise ValueError(f"unknown service: {service}")


def _service_spec(service: str, cfg: Config) -> ServiceSpec:
    if service == "proxy":
        return ServiceSpec(
            name="proxy",
            host=cfg.proxy.host,
            preferred_port=cfg.proxy.port,
            range_start=cfg.services.proxy_port_range_start,
            range_end=cfg.services.proxy_port_range_end,
            health_path="/healthz",
            expected_service_marker="proxy",
            start_cmd=cfg.services.proxy_start_cmd,
            cmd_signature="session-forge proxy",
        )

    if service == "mcp_server":
        return ServiceSpec(
            name="mcp_server",
            host=cfg.mcp_server.host,
            preferred_port=cfg.mcp_server.port,
            range_start=cfg.services.mcp_server_port_range_start,
            range_end=cfg.services.mcp_server_port_range_end,
            health_path="/healthz",
            expected_service_marker="mcp_server",
            start_cmd=cfg.services.mcp_server_start_cmd,
            cmd_signature="session-forge mcp-server",
        )

    if service == "llama":
        host, preferred_port = _url_host_port(cfg.llama.server_url, 8080)
        return ServiceSpec(
            name="llama",
            host=host,
            preferred_port=preferred_port,
            range_start=cfg.services.llama_port_range_start,
            range_end=cfg.services.llama_port_range_end,
            health_path="/health",
            expected_service_marker=None,
            start_cmd=cfg.services.llama_start_cmd,
            cmd_signature="llama-server",
        )

    raise ValueError(f"unknown service: {service}")


async def _health_matches(spec: ServiceSpec, port: int) -> bool:
    url = f"http://{spec.host}:{port}{spec.health_path}"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(url)
    except Exception:
        return False

    if resp.status_code != 200:
        return False

    if spec.expected_service_marker is None:
        return True

    try:
        payload = resp.json()
    except Exception:
        return False

    return payload.get("service") == spec.expected_service_marker


async def _is_valid_instance(spec: ServiceSpec, pid: int, port: int) -> bool:
    if not _pid_alive(pid):
        return False
    if not _cmd_matches_signature(_cmdline_for_pid(pid), spec.cmd_signature):
        return False
    return await _health_matches(spec, port)


async def _discover_running(spec: ServiceSpec) -> tuple[int, int] | None:
    for port in _candidate_ports(spec.preferred_port, spec.range_start, spec.range_end):
        if not _port_in_use(spec.host, port):
            continue
        pid = _pid_for_port(port)
        if pid is None:
            continue
        if await _is_valid_instance(spec, pid, port):
            return pid, port
    return None


def _replace_or_append_port_arg(args: list[str], port: int) -> list[str]:
    out = args[:]
    if "--port" in out:
        idx = out.index("--port")
        if idx + 1 < len(out):
            out[idx + 1] = str(port)
            return out
    out.extend(["--port", str(port)])
    return out


def _build_start_args(start_cmd: str, port: int) -> list[str]:
    args = shlex.split(start_cmd)
    return _replace_or_append_port_arg(args, port)


def _new_log_path(service: str) -> Path:
    return logs_dir() / f"{service}-{_ts_compact()}.log"


def _log_line(path: Path, severity: str, message: str) -> None:
    line = f"{_now_iso()} [{severity.upper()}] {message}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


async def _wait_healthy(spec: ServiceSpec, port: int, timeout_seconds: float = 12.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if await _health_matches(spec, port):
            return True
        await asyncio.sleep(0.25)
    return False


def _runtime_record(spec: ServiceSpec, pid: int, port: int, reused: bool, log_file: str | None = None) -> dict:
    rec = {
        "service_name": spec.name,
        "pid": pid,
        "port": port,
        "started_at": _now_iso(),
        "cmd_signature": spec.cmd_signature,
        "health_url": f"http://{spec.host}:{port}{spec.health_path}",
        "service_identity": spec.expected_service_marker or "llama-server",
        "reused": reused,
    }
    if log_file:
        rec["log_file"] = log_file
    return rec


async def ensure_service(service: str, allow_start: bool) -> dict:
    """Ensure a service is up and identity-validated.

    Returns structured status with configured/effective ports and whether the
    instance was reused or started.
    """
    cfg = config()
    spec = _service_spec(service, cfg)
    configured_port = _configured_port(service, cfg)

    state = read_service_state()
    existing = state.get(service, {})
    pid = existing.get("pid")
    port = existing.get("port")
    log_file = existing.get("log_file")
    if isinstance(pid, int) and isinstance(port, int):
        if await _is_valid_instance(spec, pid, port):
            _upsert_state(service, _runtime_record(spec, pid, port, reused=True, log_file=log_file))
            return {
                "service": service,
                "status": "up",
                "identity": "matched",
                "configured_port": configured_port,
                "effective_port": port,
                "action": "reused",
                "log_file": log_file,
            }

    running = await _discover_running(spec)
    if running is not None:
        pid, port = running
        _upsert_state(service, _runtime_record(spec, pid, port, reused=True, log_file=log_file))
        return {
            "service": service,
            "status": "up",
            "identity": "matched",
            "configured_port": configured_port,
            "effective_port": port,
            "action": "reused",
            "log_file": log_file,
        }

    if not allow_start:
        return {
            "service": service,
            "status": "down",
            "identity": "missing",
            "configured_port": configured_port,
            "effective_port": None,
            "action": "none",
            "log_file": log_file,
        }

    errors: list[str] = []
    for candidate in _candidate_ports(spec.preferred_port, spec.range_start, spec.range_end):
        if _port_in_use(spec.host, candidate):
            errors.append(f"port {candidate} already in use")
            continue

        args = _build_start_args(spec.start_cmd, candidate)
        log_path = _new_log_path(service)
        _log_line(log_path, "INFO", f"starting service with args: {' '.join(args)}")

        env = os.environ.copy()
        if service == "mcp_server":
            env["SF_MCP_EFFECTIVE_PORT"] = str(candidate)

        try:
            with log_path.open("a", encoding="utf-8") as logf:
                proc = subprocess.Popen(
                    args,
                    start_new_session=True,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
        except Exception as exc:
            errors.append(f"start failed on port {candidate}: {exc}")
            _log_line(log_path, "ERROR", f"start failed on port {candidate}: {exc}")
            continue

        if await _wait_healthy(spec, candidate):
            pid = _pid_for_port(candidate) or proc.pid
            _upsert_state(
                service,
                _runtime_record(spec, pid, candidate, reused=False, log_file=str(log_path)),
            )
            _log_line(log_path, "INFO", f"service is healthy on port {candidate} (pid={pid})")
            return {
                "service": service,
                "status": "up",
                "identity": "matched",
                "configured_port": configured_port,
                "effective_port": candidate,
                "action": "started",
                "cmd": " ".join(args),
                "log_file": str(log_path),
            }

        errors.append(f"health check timeout on port {candidate}")
        _log_line(log_path, "WARNING", f"health check timeout on port {candidate}")
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except Exception:
            pass

    return {
        "service": service,
        "status": "down",
        "identity": "missing",
        "configured_port": configured_port,
        "effective_port": None,
        "action": "none",
        "reason": "no available healthy port in configured range",
        "errors": errors,
        "log_file": log_file,
    }


def stop_service(service: str) -> dict:
    """Stop a managed service by pid from runtime state."""
    if service not in _MANAGED_SERVICES:
        return {"service": service, "status": "unknown", "action": "none", "reason": "unknown service"}

    state = read_service_state()
    rec = state.get(service)
    if not rec:
        return {"service": service, "status": "down", "action": "none", "reason": "not running"}

    pid = rec.get("pid")
    if not isinstance(pid, int) or not _pid_alive(pid):
        _remove_state(service)
        return {"service": service, "status": "down", "action": "none", "reason": "stale pid record"}

    log_file = rec.get("log_file")
    log_path = Path(log_file) if isinstance(log_file, str) and log_file else None
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        if log_path:
            _log_line(log_path, "ERROR", f"stop failed for pid {pid}: {exc}")
        return {"service": service, "status": "up", "action": "none", "reason": f"stop failed: {exc}"}

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.1)

    if _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    _remove_state(service)
    if log_path:
        _log_line(log_path, "INFO", f"service stopped (pid={pid})")
    return {"service": service, "status": "down", "action": "stopped", "pid": pid}


async def service_status_snapshot() -> dict:
    """Return identity-aware status for all managed services."""
    out: dict[str, dict] = {}
    for service in _MANAGED_SERVICES:
        out[service] = await ensure_service(service, allow_start=False)
    return out


async def ensure_all_daemons() -> dict:
    """Start/reuse all managed services as detached daemons."""
    out: dict[str, dict] = {}
    for service in ("llama", "proxy", "mcp_server"):
        out[service] = await ensure_service(service, allow_start=True)
    return out


def stop_all_daemons() -> dict:
    """Stop all managed services."""
    out: dict[str, dict] = {}
    for service in ("mcp_server", "proxy", "llama"):
        out[service] = stop_service(service)
    return out
