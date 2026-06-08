"""Integration tests for the /ingest endpoint."""

import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_ingest_creates_session():
    from session_forge.mcp_server.server import http_app
    from session_forge.mcp_server.storage import get_session, get_messages

    async with AsyncClient(transport=ASGITransport(app=http_app), base_url="http://test") as client:
        resp = await client.post("/ingest", json={
            "tool": "claude-code",
            "model": "claude-opus-4-5",
            "project_path": "/Users/ckim/Projects/ck-apstra-tool",
            "session_id": "test-session-001",
            "messages": [{"role": "user", "content": "hello"}],
            "response": {"content": [{"type": "text", "text": "hi there"}]},
            "latency_ms": 250,
            "output_tokens": 5,
        })

    assert resp.status_code == 200
    assert resp.json()["session_id"] == "test-session-001"

    session = get_session("test-session-001")
    assert session.tool == "claude-code"
    assert session.project_name == "ck-apstra-tool"

    messages = get_messages("test-session-001")
    assert any(m.role == "user" and "hello" in m.content for m in messages)
    assert any(m.role == "assistant" and "hi there" in m.content for m in messages)


@pytest.mark.asyncio
async def test_ingest_auto_generates_session_id():
    from session_forge.mcp_server.server import http_app

    async with AsyncClient(transport=ASGITransport(app=http_app), base_url="http://test") as client:
        resp = await client.post("/ingest", json={
            "tool": "gemini-cli",
            "messages": [{"role": "user", "content": "test"}],
        })

    assert resp.status_code == 200
    assert len(resp.json()["session_id"]) > 0


@pytest.mark.asyncio
async def test_ingest_sidecar_written(tmp_config):
    from session_forge.mcp_server.server import http_app

    async with AsyncClient(transport=ASGITransport(app=http_app), base_url="http://test") as client:
        await client.post("/ingest", json={
            "tool": "claude-code",
            "project_path": "/Users/ckim/Projects/session-forge",
            "session_id": "sidecar-test-001",
            "messages": [{"role": "user", "content": "build something"}],
        })

    sidecar_dir = tmp_config / "projects" / "session-forge" / "claude-code" / "sessions"
    files = list(sidecar_dir.glob("*.md"))
    assert len(files) == 1
    assert "session-forge" in files[0].read_text()
