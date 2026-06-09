# Proxy Design — session-forge

## Overview

The proxy sits between AI coding clients and their upstream APIs. It forwards all traffic transparently while logging request/response pairs to the MCP server.

## Per-Tool Intercept Strategy

### Claude Code
- Set `ANTHROPIC_BASE_URL=http://localhost:8888`
- Proxy receives all `/v1/messages` calls
- Forwards to `https://api.anthropic.com` with original headers

### Gemini CLI
- Set `GEMINI_API_BASE=http://localhost:8888` (or equivalent env var)
- Intercepts `/v1beta/models/*:generateContent` calls
- Forwards to `https://generativelanguage.googleapis.com`

### GitHub Copilot (Phase 2)
- Requires system-level HTTPS proxy via mitmproxy
- Set `HTTP_PROXY` / `HTTPS_PROXY` in shell profile
- Install mitmproxy CA cert into macOS Keychain
- Target domains: `*.copilot.github.com`, `*.githubcopilot.com`

## Request Flow

```
Client Request
    │
    ▼
proxy/app.py  ←─ detect tool from path/headers
    │
    ├── proxy/logger.py  ←─ extract session metadata async
    │       │
    │       └── POST /log → mcp_server (fire-and-forget)
    │
    └── proxy/forwarder.py  ←─ stream response back to client
```

## Session Detection

Tool is inferred from:
- Request path (e.g. `/v1/messages` → claude-code)
- `User-Agent` header
- API key prefix (Anthropic vs Google)

## Streaming Support

Claude Code uses SSE streaming responses. The proxy must:
1. Forward chunks to client in real-time
2. Buffer the full response for logging after stream completes
3. Never delay client-visible chunks

## Latency Budget

Logging is fully async and fire-and-forget. Target proxy overhead: < 5ms p99.

## Health Endpoints

Both the proxy and the MCP server expose a lightweight health endpoint:

| Service | Endpoint | Response |
|---|---|---|
| proxy | `GET /healthz` | `{"status": "ok", "service": "proxy"}` |
| mcp_server | `GET /healthz` | `{"status": "ok", "service": "mcp_server"}` |
| llama-server | `GET /health` | built-in llama.cpp endpoint |

These are used by the `service_status` MCP tool to determine which services are
running. The `/healthz` route is registered **before** the catch-all proxy route
so it is never forwarded upstream.

## MCP Service Management Tools

Two MCP tools are registered in `mcp_server/server.py`:

### `service_status() → dict`

Pings all three health endpoints and returns:

```json
{
  "proxy": {
    "status": "up" | "down",
    "configured_port": 8888,
    "effective_port": 8888 | null,
    "identity": "matched" | "missing",
    "action": "reused" | "none"
  },
  "mcp_server": {
    "status": "up" | "down",
    "configured_port": 8000,
    "effective_port": 8000 | null,
    "identity": "matched" | "missing",
    "action": "reused" | "none"
  },
  "llama": {
    "status": "up" | "down",
    "configured_port": 8080,
    "effective_port": 8080 | null,
    "identity": "matched" | "missing",
    "action": "reused" | "none"
  }
}
```

### `service_up(service="llama") → dict`

Brings up a service that is currently down:

- Reuses already-running services only when identity checks pass.
- Starts missing services with configured startup commands.
- If preferred port is occupied by another process, selects the next free port
  in configured range and records effective runtime port.

Both tools read configuration exclusively from
`~/.config/session-forge/config.yaml`.

Effective runtime ports and metadata are persisted to:

- `~/.config/session-forge/service-ports.json`

## Daemon Lifecycle Commands

Service lifecycle is managed through CLI runtime orchestration:

- `uv run session-forge mcp-server` starts/reuses all three services as detached daemons
  (`llama`, `proxy`, `mcp_server`) and exits after reporting status.
- `uv run session-forge services status` reports current identity-aware status.
- `uv run session-forge services stop` stops all managed daemons.
- `uv run session-forge services restart` stops and then starts all managed daemons.

Each started service instance writes to its own log file under:

- `~/.session-forge/logs/{service}-{YYYYMMDD-HHMMSS}.log`

Lifecycle logging includes explicit severity labels:

- `INFO` for startup/healthy/stopped events
- `WARNING` for health-check timeout conditions
- `ERROR` for startup/stop failures
