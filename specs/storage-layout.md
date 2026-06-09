# Storage Layout — session-forge

## Design Goals

- Global SQLite DB for cross-project analysis (harness, skill, agent improvements)
- Per-project/tool markdown tree for Obsidian browsing and project-specific insights
- Standard macOS `~/` convention — no root, no sudo, portable
- Project name = CWD basename (simple, collision-acceptable for single user)
- Self-documenting: runtime behavior is documented in `~/.config/session-forge/config.yaml`

## Directory Layout

```
~/.session-forge/
├── sessions.db                              ← global DB (all projects, tools)
└── projects/
    └── {project-name}/                      ← CWD basename, e.g. "ck-apstra-tool"
        └── {tool}/                          ← "claude-code" | "gemini-cli" | "copilot"
            ├── sessions/
            │   └── YYYY-MM-DD_<id_short>.md
            └── insights/
                └── YYYY-MM-DD_<id_short>.md
```

### Example

```
~/.session-forge/
├── sessions.db
└── projects/
    ├── ck-apstra-tool/
    │   ├── claude-code/
    │   │   ├── sessions/
    │   │   │   ├── 2026-06-08_abc12345.md
    │   │   │   └── 2026-06-08_def67890.md
    │   │   └── insights/
    │   │       └── 2026-06-08_abc12345.md
    │   └── gemini-cli/
    │       └── sessions/
    │           └── 2026-06-08_xyz11111.md
    ├── session-forge/
    │   └── claude-code/
    │       └── sessions/
    │           └── 2026-06-08_aaa22222.md
    └── my-etrade/
        └── claude-code/
            └── sessions/
                └── 2026-06-08_bbb33333.md
```

## Runtime Directory Docs

`~/.session-forge/` is data-only and contains no generated README.

Runtime configuration and storage explanation live in
`~/.config/session-forge/config.yaml`, which is written on first run and never
overwritten after creation.

## Global DB Rationale

A single `sessions.db` spanning all projects enables:
- Cross-project pattern mining: "which prompt patterns recur across all projects?"
- Generic harness/skill/agent improvements not tied to one project
- Tool-level aggregates: "how many tokens does Claude Code use vs Gemini CLI?"
- Temporal trends across the entire workspace

Project/environment-specific analysis is done by filtering on `project_name` column.

## Project Name Resolution

`project_name` = `os.path.basename(project_path)` e.g.:
- `/Users/ckim/Projects/ck-apstra-tool` → `ck-apstra-tool`
- `/Users/ckim/Projects/session-forge` → `session-forge`

Collision policy: same basename from different parent paths → same bucket.
Acceptable for single-user; full path stored separately in `project_path` column
for disambiguation when needed.

## Schema Changes

### `sessions` table — add `project_name` column

| Column | Type | Notes |
|---|---|---|
| `project_name` | TEXT | `os.path.basename(project_path)`, default `"unknown"` |

`correlation_key` updated to: `"{tool}:{project_name}"` (was `"{tool}:{project_path}"`)

## Path Helper

All path construction centralized in `session_forge/paths.py`:

```python
BASE_DIR = Path.home() / ".session-forge"

def db_path() -> Path: ...
def sessions_dir(project_name, tool) -> Path: ...
def insights_dir(project_name, tool) -> Path: ...
def project_name_from_path(project_path) -> str: ...
```

`_ensure_base_dir()` is called by every path function to ensure directories
exist before reads and writes.

## Config Changes

`settings` no longer has `sessions_dir` / `insights_dir`.
`SF_BASE_DIR` env var is removed.

## Implementation Files

| File | Change |
|---|---|
| `session_forge/paths.py` | All path construction for DB and sidecar directories |
| `session_forge/config.py` | Replaced `sessions_dir`/`insights_dir` with `storage.base_dir` in `config.yaml` |
| `mcp_server/storage.py` | Uses `paths.db_path()`; `project_name` column; WAL + StaticPool |
| `mcp_server/sidecar.py` | Uses `paths.sessions_dir()` / `paths.insights_dir()`; async-safe locks |
| `mcp_server/server.py` | Passes `project_name`; awaits async sidecar writer |
| `session_forge/cli.py` | `list-sessions --project` filter; `show-paths` command |
| `.env.example` | Deleted |

## References

- Session correlation: `specs/session-correlation.md`
- Concurrency: `specs/concurrency.md`
- Project detection: `specs/project-detection.md`
