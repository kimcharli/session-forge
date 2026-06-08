"""Configuration — loaded from ~/.config/session-forge/config.yaml.

Written with defaults and full comments on first run.
Never overwritten once created.
Override config file path with SF_CONFIG env var (testing only).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# ── Default config.yaml content ───────────────────────────────────────────────

_DEFAULT_YAML = """\
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
"""

# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class ProxyConfig:
    host: str = "127.0.0.1"
    port: int = 8888


@dataclass
class McpServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


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


# ── Config file path ──────────────────────────────────────────────────────────

def config_path() -> Path:
    """Return config file path. SF_CONFIG env var overrides (testing only)."""
    override = os.environ.get("SF_CONFIG")
    if override:
        return Path(override)
    return Path.home() / ".config" / "session-forge" / "config.yaml"


def _ensure_config() -> Path:
    """Write default config.yaml on first run. Never overwrites."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(_DEFAULT_YAML, encoding="utf-8")
    return path


# ── Loader ────────────────────────────────────────────────────────────────────

def _load() -> Config:
    path = _ensure_config()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def _section(key, cls):
        data = raw.get(key, {}) or {}
        defaults = cls()
        for f in defaults.__dataclass_fields__:
            if f in data:
                setattr(defaults, f, data[f])
        return defaults

    return Config(
        proxy=_section("proxy", ProxyConfig),
        mcp_server=_section("mcp_server", McpServerConfig),
        llama=_section("llama", LlamaConfig),
        storage=_section("storage", StorageConfig),
        session=_section("session", SessionConfig),
    )


# ── Singleton ─────────────────────────────────────────────────────────────────

_config: Config | None = None


def config() -> Config:
    """Return cached config. Call reset_config() between tests."""
    global _config
    if _config is None:
        _config = _load()
    return _config


def reset_config() -> None:
    """Reset cached config — use in tests when SF_CONFIG changes."""
    global _config
    _config = None
