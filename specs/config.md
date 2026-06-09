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
# This file is never overwritten by session-forge once created.

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

## Loading Priority

1. `~/.config/session-forge/config.yaml` (primary)
2. `SF_CONFIG` env var — override config file path (for testing only)
3. Hard-coded defaults in `Config` dataclass (fallback if file missing)

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
