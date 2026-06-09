"""FastMCP server + FastAPI /ingest endpoint."""

import shlex
import subprocess
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastmcp import FastMCP
from pydantic import BaseModel

from session_forge.mcp_server import sidecar, storage
from session_forge.paths import project_name_from_path


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


async def _check(url: str) -> bool:
    """Return True if url responds 200, False otherwise."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(url)
            return r.status_code == 200
    except Exception:
        return False


@mcp.tool()
async def service_status() -> dict:
    """Check whether proxy, mcp_server, and llama-server are reachable.

    Returns a dict with keys proxy, mcp_server, llama — each "up" or "down".
    Configuration is read from ~/.config/session-forge/config.yaml.
    """
    from session_forge.config import config
    cfg = config()
    proxy_url = f"http://{cfg.proxy.host}:{cfg.proxy.port}/healthz"
    mcp_url = f"{cfg.mcp_server.url}/healthz"
    llama_url = f"{cfg.llama.server_url}/health"

    proxy_up, mcp_up, llama_up = await _check(proxy_url), await _check(mcp_url), await _check(llama_url)
    return {
        "proxy": "up" if proxy_up else "down",
        "mcp_server": "up" if mcp_up else "down",
        "llama": "up" if llama_up else "down",
        "proxy_url": proxy_url,
        "mcp_url": mcp_url,
        "llama_url": llama_url,
    }


@mcp.tool()
async def service_up(service: str = "llama") -> dict:
    """Start a service if it is currently down.

    Only llama-server can be started automatically — its startup command is
    read from services.llama_start_cmd in config.yaml.

    proxy and mcp_server must be started via the CLI (session-forge proxy /
    session-forge mcp-server), because they are typically the callers of this
    MCP server.

    Args:
        service: one of "llama", "proxy", "mcp_server". Defaults to "llama".
    """
    from session_forge.config import config
    cfg = config()

    if service == "llama":
        llama_url = f"{cfg.llama.server_url}/health"
        if await _check(llama_url):
            return {"service": "llama", "action": "none", "reason": "already up"}
        cmd = shlex.split(cfg.services.llama_start_cmd)
        subprocess.Popen(cmd, start_new_session=True)
        return {
            "service": "llama",
            "action": "started",
            "cmd": cfg.services.llama_start_cmd,
            "note": "started in background; check service_status in a few seconds",
        }

    if service in ("proxy", "mcp_server"):
        return {
            "service": service,
            "action": "none",
            "reason": f"{service} must be started manually: uv run session-forge {service.replace('_', '-')}",
        }

    return {"service": service, "action": "none", "reason": f"unknown service: {service}"}


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
