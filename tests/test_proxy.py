"""Smoke tests for proxy tool detection and payload building."""

from unittest.mock import MagicMock

from session_forge.proxy.logger import detect_tool, _build_payload


def make_mock_request(user_agent: str = "") -> MagicMock:
    req = MagicMock()
    req.headers = {"user-agent": user_agent}
    return req


def test_detect_claude_code():
    assert detect_tool(make_mock_request(), "v1/messages") == "claude-code"


def test_detect_gemini():
    assert detect_tool(make_mock_request(), "v1beta/models/gemini-2.0-flash:generateContent") == "gemini-cli"


def test_detect_copilot_by_path():
    assert detect_tool(make_mock_request(), "copilot/v1/engines") == "copilot"


def test_detect_copilot_by_ua():
    assert detect_tool(make_mock_request(user_agent="github-copilot/1.0"), "other/path") == "copilot"


def test_detect_unknown():
    assert detect_tool(make_mock_request(), "some/other/path") is None


def test_build_payload_anthropic():
    req = b'{"model":"claude-opus-4-5","messages":[{"role":"user","content":"hello"}]}'
    resp = b'{"content":[{"type":"text","text":"hi"}],"usage":{"input_tokens":10,"output_tokens":5}}'
    payload = _build_payload("claude-code", req, resp, 300)
    assert payload["tool"] == "claude-code"
    assert payload["model"] == "claude-opus-4-5"
    assert payload["input_tokens"] == 10
    assert payload["output_tokens"] == 5
    assert payload["latency_ms"] == 300
    assert payload["messages"] == [{"role": "user", "content": "hello"}]


def test_build_payload_gemini():
    req = b'{"model":"gemini-2.0-flash","contents":[{"role":"user","parts":[{"text":"hi"}]}]}'
    resp = b'{"usageMetadata":{"promptTokenCount":5,"candidatesTokenCount":3}}'
    payload = _build_payload("gemini-cli", req, resp, 150)
    assert payload["tool"] == "gemini-cli"
    assert payload["input_tokens"] == 5
    assert payload["output_tokens"] == 3


def test_build_payload_malformed_bodies():
    payload = _build_payload("claude-code", b"not-json", b"also-not-json", 50)
    assert payload["tool"] == "claude-code"
    assert payload["model"] is None
    assert payload["messages"] == []
