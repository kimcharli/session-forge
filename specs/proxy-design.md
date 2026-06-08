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
