# session-forge

> ⚠️ **Status: Active development — pre-alpha. See [STATUS.md](STATUS.md) for what works and what doesn't.**

Local MCP server + HTTPS proxy that intercepts AI coding sessions (Claude Code, Gemini CLI, GitHub Copilot), stores them locally, and uses a local LLM (llama.cpp) to analyze and recommend improvements to prompts, harness, and skills.

## Architecture

```
Claude Code ──┐
Gemini CLI  ──┼──► proxy/  (FastAPI HTTPS proxy)
Copilot     ──┘      │
                     ├── forward to real API
                     └── log to mcp_server/
                               │
                    ┌──────────┴──────────┐
                    │  MCP Server         │
                    │  - SQLite storage   │
                    │  - Markdown sidecar │
                    │  - Analysis queue   │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  analyzer/          │
                    │  llama.cpp client   │
                    │  Qwen2.5-Coder-14B  │
                    └─────────────────────┘
```

## Components

| Path | Purpose |
|---|---|
| `src/session_forge/proxy/` | FastAPI HTTPS proxy — intercepts and forwards AI client traffic |
| `src/session_forge/mcp_server/` | FastMCP server — stores sessions, exposes analysis tools |
| `src/session_forge/analyzer/` | llama.cpp HTTP client — session analysis and insight generation |
| `specs/` | SDD specs — design decisions, schemas, agent contracts |
| `~/.config/session-forge/config.yaml` | Runtime config — written with defaults on first run |
| `~/.session-forge/` | Runtime data — SQLite DB + per-project markdown sidecars |

## Quick Start

```bash
# Install
uv sync

# Show config and data paths (creates config.yaml on first run)
uv run session-forge show-paths

# Edit config if needed
uv run session-forge edit-config

# Start the MCP server
uv run session-forge mcp-server

# Start the proxy (Claude Code intercept)
uv run session-forge proxy

# Point Claude Code at the proxy
export ANTHROPIC_BASE_URL=http://127.0.0.1:8888
```

## LLM Backend

Requires [llama.cpp](https://github.com/ggerganov/llama.cpp) with Metal build on Apple Silicon.

Recommended model: `Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf` (~9GB VRAM)

```bash
llama-server --model ~/models/Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf \
  --port 8080 --ctx-size 8192 --n-gpu-layers 99
```

## Session Storage

All data lives under `~/.session-forge/`:

```
~/.session-forge/
├── sessions.db                        # global SQLite DB — all projects and tools
└── projects/
    └── {project-name}/
        └── {tool}/
            ├── sessions/              # per-session markdown transcripts
            └── insights/              # LLM-generated recommendations
```

## License

MIT — see [LICENSE](LICENSE).
