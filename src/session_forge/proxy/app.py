"""FastAPI proxy app — intercepts AI client traffic and logs to MCP server."""

import json
import time
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

from session_forge.proxy.forwarder import forward_request
from session_forge.proxy.logger import detect_tool, log_session_turn


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=120.0)
    yield
    await app.state.http_client.aclose()


app = FastAPI(title="session-forge proxy", lifespan=lifespan)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(request: Request, path: str):
    from session_forge.config import config
    tool = detect_tool(request, path)
    upstream_url = _resolve_upstream(tool, path, str(request.url))

    body = await request.body()
    start_ms = time.monotonic()

    response, full_body = await forward_request(
        client=request.app.state.http_client,
        method=request.method,
        url=upstream_url,
        headers=dict(request.headers),
        body=body,
    )

    latency_ms = int((time.monotonic() - start_ms) * 1000)

    if tool and body:
        import asyncio
        asyncio.create_task(
            log_session_turn(
                tool=tool,
                request_body=body,
                response_body=full_body,
                latency_ms=latency_ms,
                mcp_url=config().mcp_server.url,
            )
        )

    if _is_streaming(body):
        return StreamingResponse(
            content=iter([full_body]),
            status_code=response.status_code,
            headers=dict(response.headers),
        )

    return Response(
        content=full_body,
        status_code=response.status_code,
        headers=dict(response.headers),
    )


def _resolve_upstream(tool: str | None, path: str, original_url: str) -> str:
    match tool:
        case "claude-code":
            return f"https://api.anthropic.com/{path}"
        case "gemini-cli":
            return f"https://generativelanguage.googleapis.com/{path}"
        case _:
            parsed = urlparse(original_url)
            return f"{parsed.path}{'?' + parsed.query if parsed.query else ''}"


def _is_streaming(body: bytes) -> bool:
    try:
        return bool(json.loads(body).get("stream"))
    except Exception:
        return False
