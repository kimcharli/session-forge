# Schema Design — session-forge

## SQLite Tables (SQLModel)

### `sessions`
| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID, generated at proxy |
| `tool` | TEXT | `claude-code`, `gemini-cli`, `copilot` |
| `model` | TEXT | e.g. `claude-opus-4-5`, `gemini-2.0-flash` |
| `project_name` | TEXT | `os.path.basename(project_path)`, default `"unknown"` |
| `project_path` | TEXT | Full CWD at session start; default `"unknown"` (see `specs/project-detection.md`) |
| `correlation_key` | TEXT | `"{tool}:{project_name}"` — indexed; used for session grouping |
| `git_branch` | TEXT | Active branch if detectable |
| `started_at` | DATETIME | |
| `ended_at` | DATETIME | nullable |
| `last_seen_at` | DATETIME | Updated on every turn; drives session timeout logic |
| `message_count` | INT | updated on each turn |
| `total_input_tokens` | INT | |
| `total_output_tokens` | INT | |

**Indexes:**
- `CREATE INDEX idx_sessions_correlation ON sessions(correlation_key, last_seen_at)`
- `CREATE INDEX idx_sessions_project ON sessions(project_name, tool, started_at)`

### `messages`
| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID |
| `session_id` | TEXT FK | → sessions.id |
| `turn_index` | INT | 0-based within session |
| `role` | TEXT | `user`, `assistant`, `system` |
| `content` | TEXT | Full message content |
| `input_tokens` | INT | nullable |
| `output_tokens` | INT | nullable |
| `latency_ms` | INT | response latency |
| `created_at` | DATETIME | |

### `insights`
| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID |
| `session_id` | TEXT FK | → sessions.id |
| `category` | TEXT | `harness`, `skill`, `agent`, `prompt-pattern` |
| `severity` | TEXT | `suggestion`, `warning`, `improvement` |
| `summary` | TEXT | One-line recommendation |
| `detail` | TEXT | Full markdown recommendation body |
| `applied_at` | DATETIME | nullable — set when human applies |
| `created_at` | DATETIME | |

### `annotations`
| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID |
| `message_id` | TEXT FK | → messages.id |
| `tag` | TEXT | e.g. `repetitive-context`, `good-pattern`, `missed-skill` |
| `note` | TEXT | Free text |
| `created_at` | DATETIME | |

---

## MCP Tool Responses

### `service_status`

```json
{
  "proxy": {
    "status": "up" | "down",
    "identity": "matched" | "missing",
    "configured_port": 8888,
    "effective_port": 8888 | null,
    "action": "reused" | "none",
    "log_file": "~/.session-forge/logs/proxy-*.log" | null
  },
  "mcp_server": {
    "status": "up" | "down",
    "identity": "matched" | "missing",
    "configured_port": 8000,
    "effective_port": 8000 | null,
    "action": "reused" | "none",
    "log_file": "~/.session-forge/logs/mcp_server-*.log" | null
  },
  "llama": {
    "status": "up" | "down",
    "identity": "matched" | "missing",
    "configured_port": 8080,
    "effective_port": 8080 | null,
    "action": "reused" | "none",
    "log_file": "~/.session-forge/logs/llama-*.log" | null
  }
}
```

### `service_up`

```json
{
  "service": "llama",
  "status": "up" | "down",
  "identity": "matched" | "missing",
  "configured_port": 8080,
  "effective_port": 8081 | null,
  "action": "started" | "reused" | "none",
  "cmd": "<resolved start command>",
  "reason": "<optional reason when down>",
  "log_file": "~/.session-forge/logs/llama-*.log" | null
}
```

Runtime state persists these service records to:

- `~/.config/session-forge/service-ports.json`

and includes `log_file` for daemon instances started by runtime orchestration.

---

## Known Gaps & Spec References

| Gap | Spec |
|---|---|
| Storage layout and base directory | `specs/storage-layout.md` |
| Session continuity across turns | `specs/session-correlation.md` |
| Concurrent write safety | `specs/concurrency.md` |
| Project path resolution | `specs/project-detection.md` |

---

## Markdown Sidecar Format

File: `~/.session-forge/projects/{project_name}/{tool}/sessions/YYYY-MM-DD_<id_short>.md`

```markdown
---
id: <uuid>
tool: claude-code
model: claude-opus-4-5
project_name: ck-apstra-tool
project_path: /Users/ckim/Projects/ck-apstra-tool
branch: main
started_at: 2026-06-08T10:00:00
---

# Session: claude-code — 2026-06-08 [ck-apstra-tool]

## Turn 1 — 10:00:01 (user)
<message content>

## Turn 1 — 10:00:03 (assistant) [342ms, 128tok in / 512tok out]
<message content>

---
*Analyzed: 2026-06-08T10:05:00 | Insights: 2*
```

---

## Insight Markdown Format

File: `~/.session-forge/projects/{project_name}/{tool}/insights/YYYY-MM-DD_<id_short>.md`

```markdown
---
session_id: <uuid>
tool: claude-code
project_name: ck-apstra-tool
generated_at: 2026-06-08T10:05:00
model: Qwen2.5-Coder-14B
---

# Insights — claude-code / ck-apstra-tool — 2026-06-08

## [harness] Missing project context in system prompt
**Severity:** improvement
The session repeatedly re-established project context in user turns.
Consider adding standard project boilerplate to the harness system prompt.

## [skill] Apstra blueprint query pattern reused 3x
**Severity:** suggestion
Extract into a reusable skill: `apstra-blueprint-query`.
```
