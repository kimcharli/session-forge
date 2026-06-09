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
  "proxy":      "up" | "down",
  "mcp_server": "up" | "down",
  "llama":      "up" | "down"
}
```

### `service_up(service="llama") → dict`

Brings up a service that is currently down:

- `"llama"` — reads `services.llama_start_cmd` from config.yaml and launches it
  with `subprocess.Popen(..., start_new_session=True)`. Returns immediately;
  caller should poll `service_status` to confirm startup.
- `"proxy"` / `"mcp_server"` — returns the CLI command the user must run;
  cannot be auto-started because they are the callers of the MCP server.

Both tools read configuration exclusively from
`~/.config/session-forge/config.yaml`.
