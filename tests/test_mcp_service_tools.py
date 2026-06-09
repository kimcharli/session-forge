"""Tests for MCP service management tools."""

import pytest


@pytest.mark.asyncio
async def test_service_status_returns_runtime_snapshot(monkeypatch):
    from session_forge.mcp_server import server

    async def fake_snapshot():
        return {
            "proxy": {"status": "up", "effective_port": 8888},
            "mcp_server": {"status": "up", "effective_port": 8000},
            "llama": {"status": "down", "effective_port": None},
        }

    monkeypatch.setattr(server, "service_status_snapshot", fake_snapshot)

    result = await server.service_status()

    assert result["proxy"]["status"] == "up"
    assert result["llama"]["status"] == "down"


@pytest.mark.asyncio
async def test_service_up_unknown_service():
    from session_forge.mcp_server import server

    result = await server.service_up("bad-service")

    assert result["action"] == "none"
    assert "unknown service" in result["reason"]


@pytest.mark.asyncio
async def test_service_up_delegates_to_runtime(monkeypatch):
    from session_forge.mcp_server import server

    async def fake_ensure(service: str, allow_start: bool):
        assert service == "llama"
        assert allow_start is True
        return {"service": "llama", "status": "up", "action": "started", "effective_port": 8080}

    monkeypatch.setattr(server, "ensure_service", fake_ensure)

    result = await server.service_up("llama")

    assert result["service"] == "llama"
    assert result["action"] == "started"
