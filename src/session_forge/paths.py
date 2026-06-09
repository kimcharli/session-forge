"""Centralized path construction for ~/.session-forge/ layout.

All storage paths are derived from config().storage.base_dir.
Config lives at ~/.config/session-forge/config.yaml (written on first run).

Layout:
    ~/.session-forge/
    ├── sessions.db
    └── projects/
        └── {project_name}/
            └── {tool}/
                ├── sessions/   ← markdown sidecars
                └── insights/   ← insight markdown
"""

from pathlib import Path


def _base_dir() -> Path:
    from session_forge.config import config
    return Path(config().storage.base_dir).expanduser().resolve()


def _ensure_base_dir() -> Path:
    base = _base_dir()
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    """Global SQLite DB — spans all projects and tools."""
    return _ensure_base_dir() / "sessions.db"


def sessions_dir(project_name: str, tool: str) -> Path:
    """Markdown sidecar directory for a given project + tool."""
    path = _ensure_base_dir() / "projects" / project_name / tool / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def insights_dir(project_name: str, tool: str) -> Path:
    """Insight markdown directory for a given project + tool."""
    path = _ensure_base_dir() / "projects" / project_name / tool / "insights"
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_name_from_path(project_path: str | None) -> str:
    """Derive project_name from full path — basename only."""
    if not project_path or project_path == "unknown":
        return "unknown"
    return Path(project_path).name or "unknown"


def config_path() -> Path:
    """Expose config file path for CLI display."""
    from session_forge.config import config_path as _cp
    return _cp()


def service_ports_path() -> Path:
    """Runtime service port file under ~/.config/session-forge/."""
    p = config_path().parent / "service-ports.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("{}\n", encoding="utf-8")
    return p


def logs_dir() -> Path:
    """Persistent logs directory for daemonized services."""
    path = _ensure_base_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
