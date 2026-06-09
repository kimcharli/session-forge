"""Shared test fixtures."""

import os

import pytest

_DEFAULT_CONFIG = """\
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
  base_dir: {base_dir}
session:
  timeout_seconds: 300
services:
  fallback_port_pool:
    start: 8000
    end: 8099
"""


@pytest.fixture(autouse=True)
def tmp_config(tmp_path):
    """Write a temp config.yaml pointing storage at tmp_path, reset all singletons."""
    base = tmp_path / ".session-forge"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(_DEFAULT_CONFIG.format(base_dir=str(base)))

    os.environ["SF_CONFIG"] = str(cfg_path)

    import session_forge.config as cfg_mod
    import session_forge.mcp_server.storage as storage_mod
    cfg_mod.reset_config()
    storage_mod._engine = None

    yield base

    cfg_mod.reset_config()
    storage_mod._engine = None
    os.environ.pop("SF_CONFIG", None)
