"""Markdown sidecar writer — generates Obsidian-browsable session files.

Files written to:
  ~/.session-forge/projects/{project_name}/{tool}/sessions/YYYY-MM-DD_<id_short>.md
  ~/.session-forge/projects/{project_name}/{tool}/insights/YYYY-MM-DD_<id_short>.md
"""

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from session_forge.paths import insights_dir, sessions_dir

# Per-session async locks — prevents concurrent writes corrupting the same file
_session_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def write_session_sidecar(
    session_id: str,
    tool: str,
    model: str | None,
    project_name: str,
    project_path: str | None,
    git_branch: str | None,
    started_at: datetime,
    messages: list[dict],
    insight_count: int = 0,
) -> Path:
    """Async-safe write of session markdown sidecar."""
    async with _session_locks[session_id]:
        return _write_session_sidecar_sync(
            session_id=session_id,
            tool=tool,
            model=model,
            project_name=project_name,
            project_path=project_path,
            git_branch=git_branch,
            started_at=started_at,
            messages=messages,
            insight_count=insight_count,
        )


def _write_session_sidecar_sync(
    session_id: str,
    tool: str,
    model: str | None,
    project_name: str,
    project_path: str | None,
    git_branch: str | None,
    started_at: datetime,
    messages: list[dict],
    insight_count: int = 0,
) -> Path:
    date_str = started_at.strftime("%Y-%m-%d")
    short_id = session_id[:8]
    path = sessions_dir(project_name, tool) / f"{date_str}_{short_id}.md"

    lines = [
        "---",
        f"id: {session_id}",
        f"tool: {tool}",
        f"model: {model or 'unknown'}",
        f"project_name: {project_name}",
        f"project_path: {project_path or 'unknown'}",
        f"branch: {git_branch or 'unknown'}",
        f"started_at: {started_at.isoformat()}",
        "---",
        "",
        f"# Session: {tool} — {date_str} [{project_name}]",
        "",
    ]

    for msg in messages:
        ts = msg.get("created_at", "")
        role = msg.get("role", "unknown")
        idx = msg.get("turn_index", "?")
        content = msg.get("content", "")

        meta = f"Turn {idx} — {ts} ({role})"
        if role == "assistant":
            lat = msg.get("latency_ms")
            inp = msg.get("input_tokens")
            out = msg.get("output_tokens")
            if lat or inp or out:
                meta += f" [{lat}ms, {inp}tok in / {out}tok out]"

        lines += [f"## {meta}", "", content, ""]

    lines += ["---"]
    if insight_count:
        lines.append(f"*Analyzed: {datetime.now(timezone.utc).isoformat()} | Insights: {insight_count}*")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_insight_sidecar(
    session_id: str,
    tool: str,
    project_name: str,
    insights: list[dict],
    generated_at: datetime | None = None,
    model: str = "unknown",
) -> Path:
    """Write insight recommendations markdown."""
    generated_at = generated_at or datetime.now(timezone.utc)
    date_str = generated_at.strftime("%Y-%m-%d")
    short_id = session_id[:8]
    path = insights_dir(project_name, tool) / f"{date_str}_{short_id}.md"

    lines = [
        "---",
        f"session_id: {session_id}",
        f"tool: {tool}",
        f"project_name: {project_name}",
        f"generated_at: {generated_at.isoformat()}",
        f"model: {model}",
        "---",
        "",
        f"# Insights — {tool} / {project_name} — {date_str}",
        "",
    ]

    for ins in insights:
        cat = ins.get("category", "unknown")
        sev = ins.get("severity", "suggestion")
        summary = ins.get("summary", "")
        detail = ins.get("detail", "")
        lines += [
            f"## [{cat}] {summary}",
            f"**Severity:** {sev}",
            "",
            detail,
            "",
        ]

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
