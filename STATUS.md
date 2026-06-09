# Status — session-forge

> Last updated: 2026-06-09

## Phase: Active Development — Pre-Alpha

Core storage and ingest pipeline are functional and tested.
Daemon lifecycle management for llama/proxy/mcp_server is implemented.
Proxy intercept, session correlation, and project detection are not yet implemented.
Not ready for daily use.

### Active Workstream

- Session continuity and project detection implementation:
	- Track follow-on work in `specs/session-correlation.md` and `specs/project-detection.md`

---

## What Works (tested, 35/35 passing)

| Component | Status | Notes |
|---|---|---|
| `config.py` | ✅ Done | YAML loader, dataclasses, singleton, `SF_CONFIG` test override |
| `paths.py` | ✅ Done | `~/.session-forge/` layout, auto-creates dirs |
| `mcp_server/storage.py` | ✅ Done | SQLModel schema, WAL mode, CRUD, project filtering |
| `mcp_server/sidecar.py` | ✅ Done | Async-safe markdown writer, per-session locks |
| `mcp_server/server.py` | ✅ Done | `/ingest` endpoint, FastMCP tools |
| `service_runtime.py` | ✅ Done | Identity-aware reuse, daemon orchestration, fallback ports, runtime state-file writes, per-instance log files |
| `proxy/logger.py` | ✅ Done | Tool detection, Anthropic + Gemini payload parsing |
| `proxy/forwarder.py` | ✅ Scaffolded | Basic forwarding works; SSE streaming incomplete |
| `proxy/app.py` | ✅ Scaffolded | Routes and forwards; untested against live traffic |
| `analyzer/prompts.py` | ✅ Done | Prompt templates |
| `analyzer/client.py` | ✅ Scaffolded | llama-server client written; no llama.cpp running yet |
| `cli.py` services commands | ✅ Done | `services start/status/stop/restart` and daemon-first `mcp-server` |

---

## Specced but Not Implemented

| Feature | Spec | Notes |
|---|---|---|
| Session correlation | `specs/session-correlation.md` | Every turn still gets a new session_id |
| Project detection | `specs/project-detection.md` | `project_path` always `"unknown"`; no wrapper scripts |
| `/register-session` endpoint | `specs/project-detection.md` | Not in `server.py` yet |
| Runtime test edge cases | `specs/implementation-tasks.md` | Core daemon/runtime scenarios are covered; keep extending integration coverage |
| Wrapper scripts | `specs/project-detection.md` | `scripts/claude`, `scripts/gemini` not written |

---

## Missing Entirely

| Item | Notes |
|---|---|
| SSE streaming in proxy | Buffers full response; breaks long Claude Code sessions |
| End-to-end integration test | No live proxied request test yet |
| llama.cpp setup docs | Model download, Metal build, launch command |
| Copilot intercept | Requires mitmproxy + cert injection; not started |
| `session_registry.py` | Session continuity module; not created yet |

---

## Next Steps (suggested order)

1. `session_registry.py` — time-window + project-path session grouping
2. `scripts/claude` + `POST /register-session` — project path injection
3. SSE streaming fix in `proxy/forwarder.py`
4. Live end-to-end test with real Claude Code session
5. llama.cpp setup and first analysis run
6. Copilot intercept via mitmproxy

---

## Specs Index

| Spec | Topic |
|---|---|
| `specs/schema.md` | SQLite schema + sidecar formats |
| `specs/proxy-design.md` | Per-tool intercept strategy |
| `specs/session-correlation.md` | Session continuity across turns |
| `specs/concurrency.md` | WAL mode, sidecar write locks |
| `specs/project-detection.md` | Project path resolution strategies |
| `specs/storage-layout.md` | `~/.session-forge/` directory layout |
| `specs/config.md` | `config.yaml` design and loading |
| `specs/analysis-prompts.md` | LLM prompt templates |
| `specs/implementation-tasks.md` | Service bring-up + runtime port tracking checklist |
