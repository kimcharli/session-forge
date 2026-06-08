# Storage Layout — session-forge

## Design Goals

- Global SQLite DB for cross-project analysis (harness, skill, agent improvements)
- Per-project/tool markdown tree for Obsidian browsing and project-specific insights
- Standard macOS `~/` convention — no root, no sudo, portable
- Project name = CWD basename (simple, collision-acceptable for single user)
- Self-documenting: `README.md` written to `~/.session-forge/` on first use

## Directory Layout

```
~/.session-forge/
├── sessions.db                              ← global DB (all projects, tools)
├── README.md                                ← written on first init by paths.py
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
├── README.md
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

## README.md (auto-written)

`~/.session-forge/README.md` is written by `_ensure_base_dir()` in `paths.py`
on first use — only if it does not already exist (safe to edit manually).

Content covers: what the directory is, layout explanation, global DB rationale,
safe-to-delete notice, CLI commands for data management.

The README content is stored as `_README` constant in `session_forge/paths.py`.

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
BASE_DIR = Path.home() / ".session-forge"   # or SF_BASE_DIR env override

def db_path() -> Path: ...
def sessions_dir(project_name, tool) -> Path: ...
def insights_dir(project_name, tool) -> Path: ...
def project_name_from_path(project_path) -> str: ...
```

`_ensure_base_dir()` is called by every path function — creates the directory
and writes `README.md` on first use.

## Config Changes

`settings` no longer has `sessions_dir` / `insights_dir`.
Optional `SF_BASE_DIR` env var overrides the default `~/.session-forge` for testing.

## Implementation Files

| File | Change |
|---|---|
| `session_forge/paths.py` | All path construction + `_README` constant + `_ensure_base_dir()` |
| `session_forge/config.py` | Replaced `sessions_dir`/`insights_dir` with optional `sf_base_dir` |
| `mcp_server/storage.py` | Uses `paths.db_path()`; `project_name` column; WAL + StaticPool |
| `mcp_server/sidecar.py` | Uses `paths.sessions_dir()` / `paths.insights_dir()`; async-safe locks |
| `mcp_server/server.py` | Passes `project_name`; awaits async sidecar writer |
| `session_forge/cli.py` | `list-sessions --project` filter; `show-paths` command |
| `.env.example` | Replaced storage vars with optional `SF_BASE_DIR` |

## References

- Session correlation: `specs/session-correlation.md`
- Concurrency: `specs/concurrency.md`
- Project detection: `specs/project-detection.md`
