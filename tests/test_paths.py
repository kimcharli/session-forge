"""Tests for path construction."""


def test_db_path_created(tmp_config):
    from session_forge.paths import db_path
    p = db_path()
    assert p == tmp_config / "sessions.db"
    assert p.parent.exists()


def test_config_yaml_written(tmp_config):
    from session_forge.config import config_path
    path = config_path()
    assert path.exists()
    text = path.read_text()
    assert "proxy" in text
    assert "storage" in text


def test_config_yaml_not_overwritten(tmp_config):
    from session_forge.config import config_path, _ensure_config
    path = config_path()
    path.write_text("# custom")
    _ensure_config()
    assert path.read_text() == "# custom"


def test_sessions_dir(tmp_config):
    from session_forge.paths import sessions_dir
    p = sessions_dir("ck-apstra-tool", "claude-code")
    assert p == tmp_config / "projects" / "ck-apstra-tool" / "claude-code" / "sessions"
    assert p.exists()


def test_insights_dir(tmp_config):
    from session_forge.paths import insights_dir
    p = insights_dir("my-etrade", "gemini-cli")
    assert p == tmp_config / "projects" / "my-etrade" / "gemini-cli" / "insights"
    assert p.exists()


def test_project_name_from_path():
    from session_forge.paths import project_name_from_path
    assert project_name_from_path("/Users/ckim/Projects/ck-apstra-tool") == "ck-apstra-tool"
    assert project_name_from_path("/Users/ckim/Projects/session-forge") == "session-forge"
    assert project_name_from_path(None) == "unknown"
    assert project_name_from_path("unknown") == "unknown"
    assert project_name_from_path("") == "unknown"
