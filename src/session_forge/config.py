"""Configuration — loaded from ~/.config/session-forge/config.yaml.

Bootstrapped from the packaged default-config.yaml on first run.
Never overwritten once created.
Override config file path with SF_CONFIG env var (testing only).
"""

import os
import shlex
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlparse

import yaml

# ── Dataclasses ───────────────────────────────────────────────────────────────

def _packaged_default_config_text() -> str:
    return files("session_forge").joinpath("default-config.yaml").read_text(encoding="utf-8")


@dataclass
class ServiceConfig:
    host: str = "127.0.0.1"
    preferred_port: int = 0
    start_cmd: str = ""

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.preferred_port}"


@dataclass
class ProxyConfig(ServiceConfig):
    preferred_port: int = 8888
    start_cmd: str = "uv run session-forge proxy --foreground"


@dataclass
class McpServerConfig(ServiceConfig):
    preferred_port: int = 8000
    start_cmd: str = "uv run session-forge mcp-server --foreground"


@dataclass
class LlamaProfileConfig:
    model_name: str = "qwen2.5-coder-7b-instruct"
    hf_repo: str = "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q4_K_M"
    context_size: int = 4096
    n_gpu_layers: int = 99


def _default_llama_profiles() -> dict[str, LlamaProfileConfig]:
    return {
        "balanced_7b": LlamaProfileConfig(),
        "quality_14b": LlamaProfileConfig(
            model_name="qwen2.5-coder-14b",
            hf_repo="Qwen/Qwen2.5-Coder-14B-Instruct-GGUF:Q4_K_M",
            context_size=4096,
            n_gpu_layers=99,
        ),
    }


@dataclass
class LlamaConfig(ServiceConfig):
    preferred_port: int = 8080
    active_profile: str = "balanced_7b"
    profiles: dict[str, LlamaProfileConfig] = field(default_factory=_default_llama_profiles)

    @property
    def profile(self) -> LlamaProfileConfig:
        if self.active_profile in self.profiles:
            return self.profiles[self.active_profile]
        if self.profiles:
            return next(iter(self.profiles.values()))
        fallback = LlamaProfileConfig()
        self.profiles = {"balanced_7b": fallback}
        self.active_profile = "balanced_7b"
        return fallback

    @property
    def model_name(self) -> str:
        return self.profile.model_name

    @property
    def context_size(self) -> int:
        return self.profile.context_size

    @property
    def hf_repo(self) -> str:
        return self.profile.hf_repo

    @property
    def n_gpu_layers(self) -> int:
        return self.profile.n_gpu_layers


@dataclass
class StorageConfig:
    base_dir: str = "~/.session-forge"


@dataclass
class SessionConfig:
    timeout_seconds: int = 300


@dataclass
class PortPoolConfig:
    start: int = 8000
    end: int = 8099


@dataclass
class ServicesConfig:
    fallback_port_pool: PortPoolConfig = field(default_factory=PortPoolConfig)


@dataclass
class Config:
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    mcp_server: McpServerConfig = field(default_factory=McpServerConfig)
    llama: LlamaConfig = field(default_factory=LlamaConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    services: ServicesConfig = field(default_factory=ServicesConfig)


# ── Config file path ──────────────────────────────────────────────────────────

def config_path() -> Path:
    """Return config file path. SF_CONFIG env var overrides (testing only)."""
    override = os.environ.get("SF_CONFIG")
    if override:
        return Path(override)
    return Path.home() / ".config" / "session-forge" / "config.yaml"


def _ensure_config() -> Path:
    """Write default config.yaml on first run. Never overwrites."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(_packaged_default_config_text(), encoding="utf-8")
    return path


# ── Loader ────────────────────────────────────────────────────────────────────

def _service_host_port(data: dict, default_port: int) -> tuple[str, int]:
    host = "127.0.0.1"
    port = default_port
    if server_url := data.get("server_url"):
        parsed = urlparse(server_url)
        host = parsed.hostname or host
        port = parsed.port or port
    if "host" in data:
        host = data["host"]
    if "preferred_port" in data:
        port = int(data["preferred_port"])
    elif "port" in data:
        port = int(data["port"])
    return host, port


def _load_proxy(raw_proxy: dict, raw_services: dict) -> ProxyConfig:
    host, preferred_port = _service_host_port(raw_proxy, ProxyConfig().preferred_port)
    return ProxyConfig(
        host=host,
        preferred_port=preferred_port,
        start_cmd=raw_proxy.get("start_cmd")
        or raw_services.get("proxy_start_cmd")
        or ProxyConfig().start_cmd,
    )


def _load_mcp_server(raw_mcp_server: dict, raw_services: dict) -> McpServerConfig:
    host, preferred_port = _service_host_port(raw_mcp_server, McpServerConfig().preferred_port)
    return McpServerConfig(
        host=host,
        preferred_port=preferred_port,
        start_cmd=raw_mcp_server.get("start_cmd")
        or raw_services.get("mcp_server_start_cmd")
        or McpServerConfig().start_cmd,
    )


def _parse_llama_start_cmd(start_cmd: str) -> dict[str, str | int]:
    parsed: dict[str, str | int] = {}
    args = shlex.split(start_cmd)
    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg == "--hf-repo" and idx + 1 < len(args):
            parsed["hf_repo"] = args[idx + 1]
            idx += 2
            continue
        if arg == "--ctx-size" and idx + 1 < len(args):
            parsed["context_size"] = int(args[idx + 1])
            idx += 2
            continue
        if arg == "--n-gpu-layers" and idx + 1 < len(args):
            parsed["n_gpu_layers"] = int(args[idx + 1])
            idx += 2
            continue
        idx += 1
    return parsed


def _default_repo_for_model(model_name: str) -> str:
    if "14b" in model_name.lower():
        return "Qwen/Qwen2.5-Coder-14B-Instruct-GGUF:Q4_K_M"
    return "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q4_K_M"


def _legacy_llama_profile(raw_llama: dict, raw_services: dict) -> LlamaProfileConfig:
    defaults = LlamaProfileConfig(
        model_name="qwen2.5-coder-14b",
        hf_repo="Qwen/Qwen2.5-Coder-14B-Instruct-GGUF:Q4_K_M",
        context_size=8192,
        n_gpu_layers=99,
    )
    parsed_cmd = _parse_llama_start_cmd(raw_services.get("llama_start_cmd", ""))
    model_name = raw_llama.get("model_name", defaults.model_name)
    context_size = int(
        raw_llama.get(
            "context_size",
            parsed_cmd.get("context_size", defaults.context_size),
        )
    )
    return LlamaProfileConfig(
        model_name=model_name,
        hf_repo=str(parsed_cmd.get("hf_repo") or _default_repo_for_model(model_name)),
        context_size=context_size,
        n_gpu_layers=int(parsed_cmd.get("n_gpu_layers", defaults.n_gpu_layers)),
    )


def _load_llama(raw_llama: dict, raw_services: dict) -> LlamaConfig:
    defaults = LlamaConfig()
    host, preferred_port = _service_host_port(raw_llama, defaults.preferred_port)
    raw_profiles = raw_llama.get("profiles") or {}

    profiles: dict[str, LlamaProfileConfig] = {}
    if raw_profiles:
        for name, profile_data in raw_profiles.items():
            profile_data = profile_data or {}
            base = defaults.profiles.get(name, LlamaProfileConfig())
            profiles[name] = LlamaProfileConfig(
                model_name=profile_data.get("model_name", base.model_name),
                hf_repo=profile_data.get("hf_repo", base.hf_repo),
                context_size=int(profile_data.get("context_size", base.context_size)),
                n_gpu_layers=int(profile_data.get("n_gpu_layers", base.n_gpu_layers)),
            )
        active_profile = raw_llama.get("active_profile", defaults.active_profile)
    else:
        active_profile = raw_llama.get("active_profile", "default")
        profiles = {active_profile: _legacy_llama_profile(raw_llama, raw_services)}

    if active_profile not in profiles:
        active_profile = next(iter(profiles))

    return LlamaConfig(
        host=host,
        preferred_port=preferred_port,
        active_profile=active_profile,
        profiles=profiles,
    )


def _load_services(raw_services: dict) -> ServicesConfig:
    defaults = ServicesConfig()
    pool_data = raw_services.get("fallback_port_pool") or {}
    if pool_data:
        start = int(pool_data.get("start", defaults.fallback_port_pool.start))
        end = int(pool_data.get("end", defaults.fallback_port_pool.end))
        return ServicesConfig(fallback_port_pool=PortPoolConfig(start=start, end=end))

    legacy_starts = [
        raw_services.get("proxy_port_range_start"),
        raw_services.get("mcp_server_port_range_start"),
        raw_services.get("llama_port_range_start"),
    ]
    legacy_ends = [
        raw_services.get("proxy_port_range_end"),
        raw_services.get("mcp_server_port_range_end"),
        raw_services.get("llama_port_range_end"),
    ]
    starts = [int(value) for value in legacy_starts if value is not None]
    ends = [int(value) for value in legacy_ends if value is not None]
    if starts and ends:
        return ServicesConfig(fallback_port_pool=PortPoolConfig(start=min(starts), end=max(ends)))
    return defaults


def _section(key: str, cls):
    data = _raw_config.get(key, {}) or {}
    defaults = cls()
    for f in defaults.__dataclass_fields__:
        if f in data:
            setattr(defaults, f, data[f])
    return defaults


_raw_config: dict[str, dict] = {}


def _load() -> Config:
    global _raw_config
    path = _ensure_config()
    _raw_config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_services = _raw_config.get("services", {}) or {}

    return Config(
        proxy=_load_proxy(_raw_config.get("proxy", {}) or {}, raw_services),
        mcp_server=_load_mcp_server(_raw_config.get("mcp_server", {}) or {}, raw_services),
        llama=_load_llama(_raw_config.get("llama", {}) or {}, raw_services),
        storage=_section("storage", StorageConfig),
        session=_section("session", SessionConfig),
        services=_load_services(raw_services),
    )


# ── Singleton ─────────────────────────────────────────────────────────────────

_config: Config | None = None


def config() -> Config:
    """Return cached config. Call reset_config() between tests."""
    global _config
    if _config is None:
        _config = _load()
    return _config


def reset_config() -> None:
    """Reset cached config — use in tests when SF_CONFIG changes."""
    global _config
    _config = None
