# AGENTS.md — session-forge

## Project Purpose

Intercept, store, and analyze AI coding sessions from Claude Code, Gemini CLI, and GitHub Copilot using a local MCP server and llama.cpp backend. Generate iterative recommendations for improving prompts, harness, and skills.

## Repository Layout

```
session-forge/
├── src/
│   └── session_forge/
│       ├── __init__.py
│       ├── cli.py              # Typer CLI — proxy, mcp-server, analyze, list-sessions, show-paths, edit-config
│       ├── config.py           # YAML config loader + dataclasses
│       ├── paths.py            # All ~/.session-forge/ path construction
│       ├── proxy/
│       │   ├── app.py          # FastAPI proxy app
│       │   ├── forwarder.py    # Async HTTP forwarder
│       │   └── logger.py       # Tool detection + session logger
│       ├── mcp_server/
│       │   ├── server.py       # FastMCP tools + FastAPI /ingest endpoint
│       │   ├── storage.py      # SQLModel schema + CRUD
│       │   └── sidecar.py      # Markdown sidecar writer (async-safe)
│       └── analyzer/
│           ├── client.py       # llama-server HTTP client
│           └── prompts.py      # Analysis prompt templates
├── tests/
│   ├── conftest.py             # Shared tmp_config fixture (SF_CONFIG → temp yaml)
│   ├── test_proxy.py
│   ├── test_paths.py
│   ├── test_storage.py
│   ├── test_sidecar.py
│   └── test_ingest.py
├── specs/
│   ├── schema.md
│   ├── proxy-design.md
│   ├── analysis-prompts.md
│   ├── session-correlation.md
│   ├── concurrency.md
│   ├── project-detection.md
│   ├── storage-layout.md
│   └── config.md
├── pyproject.toml
├── AGENTS.md
└── README.md
```

## Runtime Layout (not in repo)

```
~/.config/session-forge/
└── config.yaml          ← written on first run; human-editable; never overwritten

~/.session-forge/        ← data only
├── sessions.db
└── projects/
    └── {project-name}/
        └── {tool}/
            ├── sessions/
            └── insights/
```

## Configuration

All config lives in `~/.config/session-forge/config.yaml` (XDG convention).
Written with defaults and inline comments on first run.
No `.env` file. No `pydantic-settings`. No `SF_BASE_DIR`.

Override config file path with `SF_CONFIG` env var — **tests only**.

```yaml
proxy:
  host: 127.0.0.1
  port: 8888
mcp_server:
  host: 127.0.0.1
  port: 8000
llama:
  server_url: http://127.0.0.1:8080
  model_name: qwen2.5-coder-14b
  context_size: 8192
storage:
  base_dir: ~/.session-forge
session:
  timeout_seconds: 300
```

## Coding Conventions (Python 3.14)

- Python 3.14+, managed with `uv`
- `src/` layout — package lives under `src/session_forge/`
- All imports use full `session_forge.*` paths
- No `from typing import Optional, Union, List, Dict` — use native syntax
- `type` statement (PEP 695) for aliases: `type SessionId = str`
- `match`/`case` for multi-branch dispatch
- Walrus operator `:=` for conditional extraction
- `str.removeprefix()` / `str.removesuffix()` instead of manual slicing
- No `from __future__ import annotations`
- Async-first: `async/await` throughout
- Pydantic v2 for API models; plain dataclasses for config
- SQLModel for DB schema
- Ruff with `UP` ruleset (`uv run ruff check src/`)
- No `pydantic-settings`, no `.env`

## Component Contracts

### session_forge/config.py
- Single source of truth for all runtime config
- `config()` returns cached `Config` dataclass
- `reset_config()` clears cache — required between tests
- `_ensure_config()` writes `config.yaml` on first run, never overwrites

### session_forge/paths.py
- All `~/.session-forge/` path construction
- Reads `base_dir` from `config().storage.base_dir`
- No README written to data dir — config.yaml is the self-documenting artifact

### session_forge/proxy/
- Forwards all bytes to upstream, never blocks on logging
- Reads `mcp_server.url` from `config()` at request time

### session_forge/mcp_server/
- `POST /ingest` — receives turns from proxy
- SQLite + async-safe markdown sidecar per turn
- FastMCP tools: `list_sessions`, `get_session`, `trigger_analysis`

### session_forge/analyzer/
- Reads `llama.*` from `config()`
- OpenAI-compatible `/v1/chat/completions` against llama-server

## Testing

```bash
uv run pytest -v          # all 27 tests
uv run pytest tests/test_storage.py -v   # storage only
```

Fixture in `conftest.py`: `tmp_config` writes a temp `config.yaml`, sets `SF_CONFIG`,
resets `config()` and `storage._engine` singletons before/after each test.
All tests are isolated — no shared state, no real `~/.session-forge/` touched.

## Key Design Decisions

- `src/` layout, Python 3.14 conventions
- `config.yaml` replaces both `.env` and `README.md` — single self-documenting artifact
- Global SQLite for cross-project analysis; per-project markdown tree for browsing
- WAL + StaticPool for SQLite concurrency
- Per-session asyncio.Lock for sidecar write safety
- Analysis post-hoc — insights are recommendations, human applies
