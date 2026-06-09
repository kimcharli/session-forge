"""FastMCP server + FastAPI /ingest endpoint."""

import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastmcp import FastMCP
from pydantic import BaseModel

from session_forge.mcp_server import sidecar, storage
from session_forge.paths import project_name_from_path
from session_forge.service_runtime import ensure_service, service_status_snapshot

# ── Ingest payload ─────────────────────────────────────────────────────────────

class IngestPayload(BaseModel):
    tool: str
    model: str | None = None
    messages: list[dict] = []
    response: dict = {}
    latency_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    session_id: str | None = None
    project_path: str | None = None


# ── FastAPI app ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    from session_forge.config import config
    from session_forge.service_runtime import _upsert_state, read_service_state

    cfg = config()
    host = cfg.mcp_server.host
    port = int(os.environ.get("SF_MCP_EFFECTIVE_PORT", cfg.mcp_server.preferred_port))
    existing = read_service_state().get("mcp_server", {})
    log_file = existing.get("log_file") if isinstance(existing, dict) else None
    _upsert_state(
        "mcp_server",
        {
            "service_name": "mcp_server",
            "pid": os.getpid(),
            "port": port,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cmd_signature": "session-forge mcp-server",
            "health_url": f"http://{host}:{port}/healthz",
            "service_identity": "mcp_server",
            "reused": True,
            "log_file": log_file,
        },
    )
    yield


http_app = FastAPI(title="session-forge MCP server", lifespan=lifespan)


@http_app.post("/ingest")
async def ingest(payload: IngestPayload):
    """Receive a session turn from the proxy."""
    session_id = payload.session_id or str(uuid.uuid4())
    project_path = payload.project_path or "unknown"
    project_name = project_name_from_path(project_path)

    storage.upsert_session(
        session_id=session_id,
        tool=payload.tool,
        model=payload.model,
        project_path=project_path,
    )

    messages = payload.messages or []
    for i, msg in enumerate(messages):
        storage.add_message(
            session_id=session_id,
            turn_index=i,
            role=msg.get("role", "user"),
            content=_extract_content(msg),
            input_tokens=payload.input_tokens if msg.get("role") == "user" else None,
            output_tokens=payload.output_tokens if msg.get("role") == "assistant" else None,
            latency_ms=payload.latency_ms if msg.get("role") == "assistant" else None,
        )

    if payload.response:
        resp_content = _extract_response_content(payload.response)
        if resp_content:
            storage.add_message(
                session_id=session_id,
                turn_index=len(messages),
                role="assistant",
                content=resp_content,
                output_tokens=payload.output_tokens,
                latency_ms=payload.latency_ms,
            )

    session = storage.get_session(session_id)
    all_messages = [m.model_dump() for m in storage.get_messages(session_id)]
    if session:
        await sidecar.write_session_sidecar(
            session_id=session_id,
            tool=session.tool,
            model=session.model,
            project_name=project_name,
            project_path=session.project_path,
            git_branch=session.git_branch,
            started_at=session.started_at,
            messages=all_messages,
        )

    return {"session_id": session_id, "status": "ok"}


def _extract_content(msg: dict) -> str:
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return str(content)


def _extract_response_content(resp: dict) -> str:
    # Anthropic format
    if content := resp.get("content"):
        if isinstance(content, list):
            return "\n".join(b.get("text", "") for b in content if b.get("type") == "text")
    # Gemini format
    if candidates := resp.get("candidates"):
        parts = candidates[0].get("content", {}).get("parts", [])
        return "\n".join(p.get("text", "") for p in parts)
    return ""


# ── Health endpoint ────────────────────────────────────────────────────────────

@http_app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "mcp_server"}


# ── FastMCP tools ──────────────────────────────────────────────────────────────

mcp = FastMCP("session-forge")


@mcp.tool()
async def service_status() -> dict:
    """Check proxy/mcp/llama status with identity-aware validation.

    For each service, returns configured port and effective runtime port (if
    identity-matched instance is found).
    """
    return await service_status_snapshot()


@mcp.tool()
async def service_up(service: str = "llama") -> dict:
    """Ensure the requested service is up.

    The service is reused when an identity-matched instance is already running.
    If the configured port is occupied by another process, fallback ports in the
    configured range are tried.

    Args:
        service: one of "llama", "proxy", "mcp_server". Defaults to "llama".
    """
    if service not in ("proxy", "mcp_server", "llama"):
        return {"service": service, "action": "none", "reason": f"unknown service: {service}"}
    return await ensure_service(service, allow_start=True)


@mcp.tool()
def list_sessions(limit: int = 20, project_name: str | None = None) -> list[dict]:
    """List recent sessions, optionally filtered by project_name."""
    return [s.model_dump() for s in storage.list_sessions(limit, project_name)]


@mcp.tool()
def get_session(session_id: str) -> dict:
    """Get session details and messages."""
    session = storage.get_session(session_id)
    if not session:
        return {"error": f"Session {session_id} not found"}
    messages = storage.get_messages(session_id)
    return {
        "session": session.model_dump(),
        "messages": [m.model_dump() for m in messages],
    }


@mcp.tool()
def trigger_analysis(session_id: str) -> dict:
    """Queue a session for llama.cpp analysis."""
    import asyncio

    from session_forge.analyzer.client import analyze_session
    session = storage.get_session(session_id)
    if not session:
        return {"error": f"Session {session_id} not found"}
    messages = storage.get_messages(session_id)

    async def run():
        return await analyze_session(session, messages)

    loop = asyncio.new_event_loop()
    insights = loop.run_until_complete(run())
    loop.close()
    return {"session_id": session_id, "insights": insights}
