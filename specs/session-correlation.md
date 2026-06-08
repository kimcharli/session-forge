# Session Correlation — session-forge

## Problem

The proxy currently generates a new `session_id` UUID on every `/ingest` call.
A 20-turn Claude Code conversation is logged as 20 separate single-turn sessions
instead of one cohesive session. This breaks analysis quality — the LLM cannot
see conversation arc, repetition patterns, or context drift across turns.

## Requirements

- Multiple simultaneous sessions from different tools must stay isolated
- Multiple simultaneous sessions from the same tool (different projects) must stay isolated
- Turns within a single conversation must be grouped under one `session_id`
- Must work without modifying Claude Code / Gemini CLI / Copilot clients

## Correlation Strategies Considered

| Strategy | How | Pros | Cons |
|---|---|---|---|
| **Native session ID** | Use `id` field in Anthropic response | Zero proxy logic | Per-response, not per-conversation |
| **TCP connection tracking** | Group by client socket | Accurate for HTTP/1.1 | Breaks under HTTP/2 multiplexing |
| **Time-window grouping** | Same tool + project within N seconds = same session | Simple | Fails if user pauses > window |
| **Conversation hash** | Hash of first user message | Stable | Doesn't handle resumed sessions |
| **Proxy-assigned cookie** | Proxy issues `X-Session-Id` header, client echoes it | Accurate, explicit | Clients don't echo custom headers |
| **Port-per-project** | Each project gets its own proxy port | Perfect isolation | Operationally heavy |
| **`X-Project-Path` + time-window** ✓ | Wrapper script injects header; proxy groups by (tool + project + time-window) | Practical, accurate enough | Requires wrapper script |

## Chosen Approach: Time-Window + Project Path Grouping

Group messages into a session when:
- Same `tool`
- Same `project_path` (from `X-Project-Path` header or fallback heuristic)
- `last_seen` timestamp within `SESSION_TIMEOUT_SECONDS` (default: 300s / 5 min)

A new session is created only when the timeout lapses or the project path changes.

### Session Registry

The proxy maintains an in-memory registry:

```python
# key: (tool, project_path)  →  value: (session_id, last_seen_timestamp)
_active_sessions: dict[tuple[str, str], tuple[str, float]] = {}
SESSION_TIMEOUT_SECONDS = 300
```

On each ingest:
1. Compute key `(tool, project_path)`
2. Look up registry; if exists and `now - last_seen < timeout` → reuse session_id
3. Otherwise → create new session_id, update registry
4. Update `last_seen` on every turn

### Project Path Resolution (priority order)

1. `X-Project-Path` request header (injected by wrapper script)
2. `X-Forwarded-For` + port mapping (if per-project ports are used)
3. Heuristic: extract from system prompt content if present
4. Fallback: `"unknown"` — all unknown-project turns group together per tool

## Schema Changes

Add to `sessions` table:

| Column | Type | Notes |
|---|---|---|
| `correlation_key` | TEXT | `"{tool}:{project_path}"` — index this |
| `last_seen_at` | DATETIME | Updated on every turn, used for timeout logic |

Add index: `CREATE INDEX idx_sessions_correlation ON sessions(correlation_key, last_seen_at)`

## Implementation Contract

### `proxy/session_registry.py` (new file)

```python
def get_or_create_session_id(tool: str, project_path: str) -> str:
    """Return active session_id or create new one. Thread-safe."""
    ...

def touch_session(tool: str, project_path: str) -> None:
    """Update last_seen for active session."""
    ...
```

### `proxy/logger.py` changes

- Extract `project_path` from `X-Project-Path` header before calling `log_session_turn`
- Call `get_or_create_session_id(tool, project_path)` to get stable session_id
- Pass session_id in the `/ingest` payload

### `mcp_server/storage.py` changes

- Add `correlation_key` and `last_seen_at` columns to `SessionRecord`
- `upsert_session()` must update `last_seen_at` on every call (not just on create)

## Wrapper Script

`scripts/claude-code` — thin wrapper that injects project path:

```bash
#!/bin/bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8888
export SF_PROJECT_PATH=$(pwd)
exec /path/to/real/claude "$@"
```

The proxy reads `X-Project-Path` or a custom env-based header injected by the wrapper.
Since we can't modify Claude Code itself, the wrapper sets the env and the proxy
infers project path from a session-start registration endpoint.

### Registration Endpoint (alternative to header injection)

`POST /register-session` — called by wrapper script before launching Claude Code:

```json
{ "tool": "claude-code", "project_path": "/Users/ckim/Projects/ck-apstra-tool", "pid": 12345 }
```

Proxy correlates subsequent requests by PID (read from TCP metadata on macOS via `lsof`).
This is more reliable than headers. **Preferred approach.**

## Open Questions

- [ ] Should `SESSION_TIMEOUT_SECONDS` be configurable per tool? (Copilot sessions may be shorter)
- [ ] Should session boundary be exposed as an MCP tool (`force_new_session(tool, project_path)`)?
- [ ] PID-based correlation feasibility on macOS needs validation
