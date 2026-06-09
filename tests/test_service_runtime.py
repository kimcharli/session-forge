"""Tests for service runtime orchestration."""

import json

import pytest


@pytest.mark.asyncio
async def test_ensure_service_reuses_identity_matched_runtime_record(tmp_config, monkeypatch):
    from session_forge.paths import service_ports_path
    from session_forge.service_runtime import ensure_service

    state = {
        "llama": {
            "service_name": "llama",
            "pid": 1234,
            "port": 8080,
        }
    }
    service_ports_path().write_text(json.dumps(state), encoding="utf-8")

    async def ok(*_args, **_kwargs):
        return True

    monkeypatch.setattr("session_forge.service_runtime._is_valid_instance", ok)

    result = await ensure_service("llama", allow_start=False)

    assert result["status"] == "up"
    assert result["action"] == "reused"
    assert result["effective_port"] == 8080


@pytest.mark.asyncio
async def test_ensure_service_starts_on_fallback_port_when_preferred_stolen(
    tmp_config,
    monkeypatch,
):
    from session_forge.service_runtime import ensure_service

    class DummyProc:
        pid = 5555

    def port_in_use(_host: str, port: int) -> bool:
        # preferred 8080 is occupied, fallback 8081 is free
        return port == 8080

    def fake_popen(args, start_new_session, stdout=None, stderr=None, env=None):
        assert start_new_session is True
        assert stdout is not None
        assert stderr is not None
        assert isinstance(env, dict)
        assert "--port" in args
        idx = args.index("--port")
        assert args[idx + 1] == "8081"
        return DummyProc()

    async def wait_healthy(_spec, port: int, timeout_seconds: float = 12.0):
        return port == 8081

    monkeypatch.setattr("session_forge.service_runtime._port_in_use", port_in_use)
    monkeypatch.setattr("session_forge.service_runtime._pid_for_port", lambda _port: 5555)
    monkeypatch.setattr("session_forge.service_runtime._wait_healthy", wait_healthy)
    monkeypatch.setattr("session_forge.service_runtime.subprocess.Popen", fake_popen)

    result = await ensure_service("llama", allow_start=True)

    assert result["status"] == "up"
    assert result["action"] == "started"
    assert result["configured_port"] == 8080
    assert result["effective_port"] == 8081


@pytest.mark.asyncio
async def test_ensure_service_down_when_not_running_and_start_disallowed(monkeypatch):
    from session_forge.service_runtime import ensure_service

    async def none_found(_spec, recorded_port=None):
        return None

    monkeypatch.setattr("session_forge.service_runtime._discover_running", none_found)

    result = await ensure_service("proxy", allow_start=False)

    assert result["status"] == "down"
    assert result["action"] == "none"


def test_stop_service_removes_state_for_stale_pid(tmp_config):
    from session_forge.paths import service_ports_path
    from session_forge.service_runtime import read_service_state, stop_service

    service_ports_path().write_text(
        json.dumps({"proxy": {"pid": 999999, "port": 8888}}),
        encoding="utf-8",
    )

    result = stop_service("proxy")

    assert result["status"] == "down"
    assert "stale pid" in result["reason"]
    assert "proxy" not in read_service_state()
