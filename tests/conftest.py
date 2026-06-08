"""Shared test fixtures."""

import os
import pytest

_DEFAULT_CONFIG = """\
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
  base_dir: {base_dir}
session:
  timeout_seconds: 300
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
