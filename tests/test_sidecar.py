"""Tests for sidecar markdown writer."""

import asyncio
import pytest
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_write_session_sidecar_creates_file(tmp_config):
    from session_forge.mcp_server.sidecar import write_session_sidecar
    started = datetime(2026, 6, 8, 10, 0, 0, tzinfo=timezone.utc)
    path = await write_session_sidecar(
        session_id="abcd1234-0000-0000-0000-000000000000",
        tool="claude-code",
        model="claude-opus-4-5",
        project_name="ck-apstra-tool",
        project_path="/Users/ckim/Projects/ck-apstra-tool",
        git_branch="main",
        started_at=started,
        messages=[
            {"turn_index": 0, "role": "user", "content": "hello", "created_at": "10:00:01"},
            {"turn_index": 1, "role": "assistant", "content": "hi",
             "created_at": "10:00:02", "latency_ms": 300, "input_tokens": 5, "output_tokens": 3},
        ],
    )
    assert path.exists()
    text = path.read_text()
    assert "ck-apstra-tool" in text
    assert "claude-code" in text
    assert "hello" in text
    assert "300ms" in text


@pytest.mark.asyncio
async def test_concurrent_writes_no_corruption(tmp_config):
    from session_forge.mcp_server.sidecar import write_session_sidecar
    started = datetime(2026, 6, 8, tzinfo=timezone.utc)
    session_id = "aaaa0000-0000-0000-0000-000000000000"

    messages_a = [{"turn_index": 0, "role": "user", "content": "turn A", "created_at": ""}]
    messages_b = [{"turn_index": 0, "role": "user", "content": "turn B", "created_at": ""},
                  {"turn_index": 1, "role": "assistant", "content": "reply B", "created_at": ""}]

    results = await asyncio.gather(
        write_session_sidecar(session_id, "claude-code", None, "proj", None, None, started, messages_a),
        write_session_sidecar(session_id, "claude-code", None, "proj", None, None, started, messages_b),
    )
    assert results[0] == results[1]
    assert results[0].read_text(encoding="utf-8")


def test_write_insight_sidecar(tmp_config):
    from session_forge.mcp_server.sidecar import write_insight_sidecar
    generated = datetime(2026, 6, 8, 10, 5, 0, tzinfo=timezone.utc)
    path = write_insight_sidecar(
        session_id="bbbb1234-0000-0000-0000-000000000000",
        tool="claude-code",
        project_name="ck-apstra-tool",
        insights=[{
            "category": "harness", "severity": "improvement",
            "summary": "Missing project context", "detail": "Add CWD to system prompt.",
        }],
        generated_at=generated,
        model="qwen2.5-coder-14b",
    )
    assert path.exists()
    text = path.read_text()
    assert "[harness]" in text
    assert "Missing project context" in text
    assert "qwen2.5-coder-14b" in text
