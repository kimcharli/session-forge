"""Tests for storage layer."""


def test_upsert_and_get_session():
    from session_forge.mcp_server.storage import upsert_session, get_session
    s = upsert_session("sid-001", "claude-code", model="claude-opus-4-5",
                       project_path="/Users/ckim/Projects/ck-apstra-tool")
    assert s.project_name == "ck-apstra-tool"
    assert s.correlation_key == "claude-code:ck-apstra-tool"
    assert get_session("sid-001").tool == "claude-code"


def test_upsert_updates_last_seen():
    from session_forge.mcp_server.storage import upsert_session
    s1 = upsert_session("sid-002", "claude-code", project_path="/proj/foo")
    s2 = upsert_session("sid-002", "claude-code", project_path="/proj/foo")
    assert s2.last_seen_at >= s1.last_seen_at


def test_add_and_get_messages():
    from session_forge.mcp_server.storage import upsert_session, add_message, get_messages
    upsert_session("sid-003", "gemini-cli", project_path="/proj/bar")
    add_message("sid-003", 0, "user", "hello", input_tokens=10)
    add_message("sid-003", 1, "assistant", "hi", output_tokens=5, latency_ms=200)
    msgs = get_messages("sid-003")
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].latency_ms == 200


def test_message_count_increments():
    from session_forge.mcp_server.storage import upsert_session, add_message, get_session
    upsert_session("sid-004", "claude-code")
    add_message("sid-004", 0, "user", "a")
    add_message("sid-004", 1, "assistant", "b")
    assert get_session("sid-004").message_count == 2


def test_list_sessions_filter():
    from session_forge.mcp_server.storage import upsert_session, list_sessions
    upsert_session("sid-005", "claude-code", project_path="/proj/alpha")
    upsert_session("sid-006", "claude-code", project_path="/proj/beta")
    assert len(list_sessions()) == 2
    assert len(list_sessions(project_name="alpha")) == 1


def test_add_insight():
    from session_forge.mcp_server.storage import upsert_session, add_insight
    upsert_session("sid-007", "claude-code")
    ins = add_insight("sid-007", "harness", "improvement", "Missing context", "Add path.")
    assert ins.category == "harness"


def test_project_name_unknown():
    from session_forge.mcp_server.storage import upsert_session, get_session
    upsert_session("sid-008", "claude-code", project_path=None)
    s = get_session("sid-008")
    assert s.project_name == "unknown"
    assert s.correlation_key == "claude-code:unknown"
