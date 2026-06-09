# Configuration — session-forge

## Config File Location

```
~/.config/session-forge/config.yaml
```

Follows XDG Base Directory convention. Written with defaults and full comments
on first run. Human-editable. Never overwritten if it already exists.

## Data Directory

```
~/.session-forge/
├── sessions.db
└── projects/
    └── {project-name}/
        └── {tool}/
            ├── sessions/
            └── insights/
```

No README in the data directory — `config.yaml` is the self-documenting artifact.
Anyone finding `~/.session-forge/` is directed to `~/.config/session-forge/config.yaml`.

## Default config.yaml

Current implementation writes defaults from the packaged
`src/session_forge/default-config.yaml` and uses it to create
`~/.config/session-forge/config.yaml` when it is absent.

```yaml
# session-forge configuration
# Source: https://github.com/kimcharli/session-forge
#
# Data is stored under storage.base_dir:
#   {base_dir}/sessions.db          — global SQLite DB (all projects, tools)
#   {base_dir}/projects/{project}/{tool}/sessions/   — markdown transcripts
#   {base_dir}/projects/{project}/{tool}/insights/   — LLM recommendations
#
# Edit this file to change ports, model, or storage location.
# This file is copied to ~/.config/session-forge/config.yaml on first run.

proxy:
  host: 127.0.0.1
  preferred_port: 8888
  start_cmd: uv run session-forge proxy --foreground

mcp_server:
  host: 127.0.0.1
  preferred_port: 8000
  start_cmd: uv run session-forge mcp-server --foreground

llama:
  host: 127.0.0.1
  preferred_port: 8080
  active_profile: balanced_7b
  profiles:
    balanced_7b:
      model_name: qwen2.5-coder-7b-instruct
      hf_repo: Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q4_K_M
      context_size: 4096
      n_gpu_layers: 99
    quality_14b:
      model_name: qwen2.5-coder-14b
      hf_repo: Qwen/Qwen2.5-Coder-14B-Instruct-GGUF:Q4_K_M
      context_size: 4096
      n_gpu_layers: 99

storage:
  base_dir: ~/.session-forge

session:
  timeout_seconds: 300

services:
  fallback_port_pool:
    start: 8000
    end: 8099
```

## Config Consolidation

The config/runtime consolidation is implemented.

### Implemented Direction

- Store the canonical default config in `src/session_forge/default-config.yaml`.
- Create `~/.config/session-forge/config.yaml` from that bundled file on first run.
- Normalize managed services to `host` + `preferred_port`.
- Replace llama `server_url` and `services.llama_start_cmd` duplication with
  active-profile resolution under `llama`.
- Replace per-service fallback ranges with a shared fallback port pool.
- Reuse running services by checking `service-ports.json` first, while still
  honoring configured host and validating service identity.

### Current Shape

```yaml
proxy:
  host: 127.0.0.1
  preferred_port: 8888
  start_cmd: uv run session-forge proxy --foreground

mcp_server:
  host: 127.0.0.1
  preferred_port: 8000
  start_cmd: uv run session-forge mcp-server --foreground

llama:
  host: 127.0.0.1
  preferred_port: 8080
  active_profile: balanced_7b
  profiles:
    balanced_7b:
      model_name: qwen2.5-coder-7b-instruct
      hf_repo: Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q4_K_M
      context_size: 4096
      n_gpu_layers: 99
    quality_14b:
      model_name: qwen2.5-coder-14b
      hf_repo: Qwen/Qwen2.5-Coder-14B-Instruct-GGUF:Q4_K_M
      context_size: 4096
      n_gpu_layers: 99

services:
  fallback_port_pool:
    start: 8000
    end: 8099
```

### Migration Notes

- Existing configs should continue loading during transition.
- Configured host remains authoritative even when `service-ports.json` records a
  previously used runtime endpoint.
- Service identity remains the gate for reuse; a listening port alone is not
  sufficient.

## Loading Priority

1. `~/.config/session-forge/config.yaml` (primary)
2. `SF_CONFIG` env var — override config file path (for testing only)
3. Packaged default file `src/session_forge/default-config.yaml` (first-run bootstrap source)

`SF_BASE_DIR` env var is **removed**. Storage path comes from `config.yaml`
`storage.base_dir` only.

## Implementation

### `session_forge/config.py` (replace pydantic-settings with PyYAML + dataclass)

```python
@dataclass
class ProxyConfig:
    host: str = "127.0.0.1"
    port: int = 8888

@dataclass
class McpServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000

@dataclass
class LlamaConfig:
    server_url: str = "http://127.0.0.1:8080"
    model_name: str = "qwen2.5-coder-14b"
    context_size: int = 8192

@dataclass
class StorageConfig:
    base_dir: str = "~/.session-forge"

@dataclass
class SessionConfig:
    timeout_seconds: int = 300

@dataclass
class Config:
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    mcp_server: McpServerConfig = field(default_factory=McpServerConfig)
    llama: LlamaConfig = field(default_factory=LlamaConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
```

### `session_forge/paths.py` changes

- Remove `SF_BASE_DIR` env var support
- `_base_dir()` reads from `config().storage.base_dir`
- `_ensure_config_dir()` writes `config.yaml` on first run
- No `README.md` written to `~/.session-forge/`

## Services Config

`ServicesConfig` dataclass holds startup commands and fallback port ranges for
managed services.

```python
@dataclass
class ServicesConfig:
  proxy_start_cmd: str = "uv run session-forge proxy"
  mcp_server_start_cmd: str = "uv run session-forge mcp-server"
    llama_start_cmd: str = "llama-server --hf-repo ..."
  proxy_port_range_start: int = 8888
  proxy_port_range_end: int = 8898
  mcp_server_port_range_start: int = 8000
  mcp_server_port_range_end: int = 8010
  llama_port_range_start: int = 8080
  llama_port_range_end: int = 8090
```

`service_up` / runtime orchestration use these fields to:

- validate and reuse existing services by identity
- start missing services with configured commands
- choose fallback ports from configured ranges when preferred ports are occupied

Daemon lifecycle behavior:

- `uv run session-forge mcp-server` starts/reuses `llama`, `proxy`, and `mcp_server`
  as detached daemons and returns immediately.
- Companion commands are exposed under `session-forge services`:
  - `start`
  - `status`
  - `stop`
  - `restart`
- Per-instance logs are written to `~/.session-forge/logs/{service}-{timestamp}.log`
  and include severity markers (`INFO`, `WARNING`, `ERROR`).

Runtime service state is stored in:

- `~/.config/session-forge/service-ports.json`

This file tracks effective runtime ports and identity metadata for `proxy`,
`mcp_server`, and `llama`.

## Dependency Change

Remove `pydantic-settings` from dependencies.
Add `pyyaml>=6.0`.

## Packaging And Tooling Metadata

Use `uv` with modern PEP 735 dependency groups:

- Development dependencies must be declared under `[dependency-groups].dev`
- Do not use deprecated `tool.uv.dev-dependencies`
- Keep `[tool.uv]` for uv-specific behavior only (for example, `package = true`)

This prevents warnings during `uv run`, `uv sync`, and local package builds.

## Files Changed

| File | Change |
|---|---|
| `session_forge/config.py` | Replace pydantic-settings with dataclass + PyYAML loader |
| `session_forge/paths.py` | Read base_dir from config; write config.yaml on first run |
| `pyproject.toml` | Replace `pydantic-settings` with `pyyaml`; remove `.env.example` |
| `.env.example` | Delete |
| `tests/` | Replace `SF_BASE_DIR` env fixture with `SF_CONFIG` pointing to temp yaml |
| `AGENTS.md` | Update conventions |
| `specs/storage-layout.md` | Update to reflect config.yaml replaces README + .env |
| `session_forge/config.py` | Add `ServicesConfig` dataclass + `services` section to default yaml |
| `session_forge/mcp_server/server.py` | Add `service_status` and `service_up` MCP tools |
| `session_forge/proxy/app.py` | Add `/healthz` endpoint |
| `session_forge/service_runtime.py` | Add identity-aware reuse, startup, fallback port resolution, state-file writes |
| `session_forge/cli.py` | Add active/effective port display and mcp-server fallback startup behavior |
