"""Session logger — detects tool type and ships turn data to MCP server."""

import json
import logging

import httpx
from fastapi import Request

logger = logging.getLogger(__name__)

type Tool = str

# Path prefixes → tool name
_TOOL_PATH_MAP: dict[str, Tool] = {
    "/v1/messages": "claude-code",
    "/v1beta/models": "gemini-cli",
    "/v1/engines": "copilot",
    "/copilot": "copilot",
}


def detect_tool(request: Request, path: str) -> Tool | None:
    """Infer which AI tool is making the request."""
    normalized = f"/{path}"
    for prefix, tool in _TOOL_PATH_MAP.items():
        if normalized.startswith(prefix):
            return tool

    ua = request.headers.get("user-agent", "").lower()
    match ua:
        case ua if "copilot" in ua:
            return "copilot"
        case ua if "google" in ua or "gemini" in ua:
            return "gemini-cli"
        case _:
            return None


async def log_session_turn(
    tool: Tool,
    request_body: bytes,
    response_body: bytes,
    latency_ms: int,
    mcp_url: str,
) -> None:
    """Post a session turn to the MCP server (fire-and-forget)."""
    try:
        payload = _build_payload(tool, request_body, response_body, latency_ms)
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{mcp_url}/ingest", json=payload)
    except Exception as e:
        logger.warning(f"Failed to log session turn: {e}")


def _build_payload(
    tool: Tool,
    request_body: bytes,
    response_body: bytes,
    latency_ms: int,
) -> dict:
    try:
        req = json.loads(request_body)
    except Exception:
        req = {}
    try:
        resp = json.loads(response_body)
    except Exception:
        resp = {}

    return {
        "tool": tool,
        "model": req.get("model") or resp.get("model"),
        "messages": req.get("messages", []),
        "response": resp,
        "latency_ms": latency_ms,
        "input_tokens": _extract_input_tokens(resp),
        "output_tokens": _extract_output_tokens(resp),
    }


def _extract_input_tokens(resp: dict) -> int | None:
    """Extract input/prompt token count — Anthropic and Gemini formats."""
    # Anthropic: resp.usage.input_tokens
    if usage := resp.get("usage"):
        if v := usage.get("input_tokens"):
            return v
    # Gemini: resp.usageMetadata.promptTokenCount
    if meta := resp.get("usageMetadata"):
        if v := meta.get("promptTokenCount"):
            return v
    return None


def _extract_output_tokens(resp: dict) -> int | None:
    """Extract output/completion token count — Anthropic and Gemini formats."""
    # Anthropic: resp.usage.output_tokens
    if usage := resp.get("usage"):
        if v := usage.get("output_tokens"):
            return v
    # Gemini: resp.usageMetadata.candidatesTokenCount
    if meta := resp.get("usageMetadata"):
        if v := meta.get("candidatesTokenCount"):
            return v
    return None
