# Project Detection — session-forge

## Problem

`project_path` is always `None` in logged sessions. This breaks:
- Session correlation (same tool, different projects → wrongly grouped)
- Analysis quality (LLM has no project context)
- Multi-project filtering in `list-sessions`

The proxy cannot read the client's working directory natively — none of the AI
tools (Claude Code, Gemini CLI, Copilot) send CWD in their API requests.

## Strategies Considered

| Strategy | Mechanism | Accuracy | Client changes needed |
|---|---|---|---|
| **Wrapper script** | Shell wrapper sets env, calls registration endpoint | High | Yes — PATH swap |
| **Per-project proxy port** | Each project runs proxy on different port | Perfect | Yes — per-project config |
| **System prompt heuristic** | Parse project name from system prompt text | Medium | No |
| **PID → CWD lookup** | `lsof`/`proc` maps client PID to CWD | High | No |
| **mDNS/socket metadata** | Read source port, map to PID via `netstat` | Medium | No |
| **Registration endpoint** ✓ | Wrapper POSTs `{tool, project_path, pid}` before launch | High | Yes — wrapper only |

## Chosen Approach: Registration Endpoint + Wrapper Script

### Registration Flow

```
wrapper script
    │
    ├── POST /register → proxy  { tool, project_path, pid }
    │       proxy stores: pid → (tool, project_path, timestamp)
    │
    └── exec real claude-code (with ANTHROPIC_BASE_URL set)
            │
            └── requests arrive at proxy
                    proxy looks up source PID → project_path
```

### Wrapper Scripts

Location: `scripts/` (added to PATH before real binaries)

**`scripts/claude`** (Claude Code wrapper):
```bash
#!/bin/bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8888
curl -s -X POST http://127.0.0.1:8888/register-session \
  -H "Content-Type: application/json" \
  -d "{\"tool\": \"claude-code\", \"project_path\": \"$(pwd)\", \"pid\": $$}" \
  > /dev/null
exec /usr/local/bin/claude-real "$@"
```

**`scripts/gemini`** (Gemini CLI wrapper):
```bash
#!/bin/bash
export GEMINI_API_BASE=http://127.0.0.1:8888
curl -s -X POST http://127.0.0.1:8888/register-session \
  -H "Content-Type: application/json" \
  -d "{\"tool\": \"gemini-cli\", \"project_path\": \"$(pwd)\", \"pid\": $$}" \
  > /dev/null
exec /usr/local/bin/gemini-real "$@"
```

### Registration Endpoint

`POST /register-session` in `proxy/app.py`:

```python
class SessionRegistration(BaseModel):
    tool: str
    project_path: str
    pid: int

@app.post("/register-session")
async def register_session(reg: SessionRegistration):
    session_registry.register_pid(reg.tool, reg.project_path, reg.pid)
    return {"status": "ok"}
```

### PID → Project Path Lookup (fallback, no wrapper)

On macOS, infer client PID from TCP connection using `lsof`:

```python
import subprocess

def get_pid_for_connection(client_port: int) -> int | None:
    result = subprocess.run(
        ["lsof", "-i", f"TCP:{client_port}", "-n", "-P", "-F", "p"],
        capture_output=True, text=True
    )
    # Parse PID from lsof output
    ...

def get_cwd_for_pid(pid: int) -> str | None:
    result = subprocess.run(
        ["lsof", "-p", str(pid), "-d", "cwd", "-F", "n"],
        capture_output=True, text=True
    )
    # Parse CWD from lsof output
    ...
```

This approach requires no wrapper but adds ~10ms latency per request.
Use as fallback only when `X-Project-Path` header and PID registry both miss.

---

## System Prompt Heuristic (no-wrapper fallback)

Parse `project_path` from system prompt content using patterns:

```python
import re

_PATTERNS = [
    r"working (?:directory|dir)[:\s]+([^\n]+)",
    r"project[:\s]+([^\n]+)",
    r"cwd[:\s]+(/[^\n]+)",
    r"(?:you are|this is) (?:the )?([A-Za-z0-9_-]+) (?:project|codebase)",
]

def extract_project_from_system_prompt(messages: list[dict]) -> str | None:
    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            for pattern in _PATTERNS:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
    return None
```

---

## Priority Resolution Order

In `proxy/logger.py`, resolve `project_path` in this order:

1. PID registry lookup (from wrapper script registration)
2. `X-Project-Path` request header (manual or injected)
3. System prompt heuristic
4. `lsof` PID→CWD lookup (slow fallback)
5. `"unknown"`

---

## Schema Changes

Add to `sessions` table (already noted in `schema.md`):

| Column | Type | Notes |
|---|---|---|
| `project_path` | TEXT | Already exists — ensure never NULL, default `"unknown"` |

Add to proxy in-memory registry (`proxy/session_registry.py`):

```python
# pid → (tool, project_path, registered_at)
_pid_registry: dict[int, tuple[str, str, float]] = {}
PID_REGISTRY_TTL_SECONDS = 3600  # clean up stale entries hourly
```

---

## Implementation Files

| File | Change |
|---|---|
| `scripts/claude` | New wrapper script |
| `scripts/gemini` | New wrapper script |
| `proxy/app.py` | Add `POST /register-session` endpoint |
| `proxy/session_registry.py` | Add `register_pid()`, `get_project_path()` |
| `proxy/logger.py` | Resolve project_path via priority chain |
| `mcp_server/storage.py` | Default `project_path` to `"unknown"` not `None` |

## Open Questions

- [ ] Copilot wrapper — needs separate investigation (VS Code extension, not CLI)
- [ ] Should wrapper scripts live in this repo under `scripts/` with install instructions?
- [ ] `lsof` fallback: acceptable 10ms overhead or disable by default?
