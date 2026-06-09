"""Typer CLI — proxy, mcp-server, analyze, list-sessions, show-paths commands."""

import asyncio
import os

import typer
import uvicorn

app = typer.Typer(name="session-forge", help="AI session intercept, storage, and analysis.")
services_app = typer.Typer(name="services", help="Manage session-forge daemons.")


def _print_service_summary(result: dict[str, dict]) -> None:
    for name in ("proxy", "mcp_server", "llama"):
        rec = result.get(name, {})
        status = rec.get("status", "unknown")
        action = rec.get("action", "none")
        port = rec.get("effective_port")
        log_file = rec.get("log_file", "-")
        typer.echo(f"{name}: status={status} action={action} port={port} log={log_file}")


@app.command()
def proxy(
    port: int = typer.Option(None, help="Proxy listen port (default: from config)"),
    host: str = typer.Option(None, help="Proxy listen host (default: from config)"),
    foreground: bool = typer.Option(False, "--foreground", help="Run in foreground (worker mode)."),
):
    """Start proxy daemon (default) or run foreground worker."""
    from session_forge.config import config
    from session_forge.proxy.app import app as proxy_app
    from session_forge.service_runtime import ensure_service

    cfg = config().proxy
    host = host or cfg.host
    port = port or cfg.port

    if not foreground:
        rec = asyncio.run(ensure_service("proxy", allow_start=True))
        _print_service_summary({"proxy": rec})
        return

    typer.echo(f"Starting proxy on {host}:{port}")
    typer.echo(f"  Set ANTHROPIC_BASE_URL=http://{host}:{port} for Claude Code")
    uvicorn.run(proxy_app, host=host, port=port, log_level="info")


@app.command("mcp-server")
def mcp_server(
    port: int = typer.Option(None, help="MCP server listen port (default: from config)"),
    host: str = typer.Option(None, help="MCP server listen host (default: from config)"),
    foreground: bool = typer.Option(
        False,
        "--foreground",
        help="Run only MCP server in foreground (worker mode).",
    ),
):
    """Start all service daemons (default) or run MCP worker in foreground."""
    from session_forge.config import config
    from session_forge.mcp_server.server import http_app
    from session_forge.service_runtime import ensure_all_daemons

    cfg = config().mcp_server
    host = host or cfg.host

    if not foreground:
        result = asyncio.run(ensure_all_daemons())
        _print_service_summary(result)
        return

    port = port or int(os.environ.get("SF_MCP_EFFECTIVE_PORT", cfg.port))
    os.environ["SF_MCP_EFFECTIVE_PORT"] = str(port)
    typer.echo(f"Starting MCP server on {host}:{port}")
    uvicorn.run(http_app, host=host, port=port, log_level="info")


@app.command()
def analyze(
    session_id: str = typer.Argument(..., help="Session ID to analyze"),
):
    """Run llama.cpp analysis on a stored session."""
    from session_forge.analyzer.client import analyze_session
    from session_forge.config import config
    from session_forge.mcp_server import storage
    from session_forge.mcp_server.sidecar import write_insight_sidecar

    session = storage.get_session(session_id)
    if not session:
        typer.echo(f"Session {session_id} not found.", err=True)
        raise typer.Exit(1)

    messages = storage.get_messages(session_id)
    typer.echo(f"Analyzing session {session_id} ({len(messages)} messages)...")

    insights = asyncio.run(analyze_session(session, messages))

    if not insights:
        typer.echo("No insights generated.")
        return

    for ins in insights:
        storage.add_insight(
            session_id=session_id,
            category=ins.get("category", "unknown"),
            severity=ins.get("severity", "suggestion"),
            summary=ins.get("summary", ""),
            detail=ins.get("detail", ""),
        )

    path = write_insight_sidecar(
        session_id=session_id,
        tool=session.tool,
        project_name=session.project_name,
        insights=insights,
        model=config().llama.model_name,
    )
    typer.echo(f"✓ {len(insights)} insights written to {path}")


@app.command("list-sessions")
def list_sessions(
    limit: int = typer.Option(20, help="Number of sessions to show"),
    project: str = typer.Option(None, "--project", "-p", help="Filter by project name"),
):
    """List recent sessions."""
    from rich.console import Console
    from rich.table import Table

    from session_forge.mcp_server import storage

    sessions = storage.list_sessions(limit, project_name=project)
    console = Console()
    table = Table(title=f"Recent Sessions{f' [{project}]' if project else ''}")
    table.add_column("ID", style="dim", width=10)
    table.add_column("Tool")
    table.add_column("Project")
    table.add_column("Model")
    table.add_column("Messages", justify="right")
    table.add_column("Started")

    for s in sessions:
        table.add_row(
            s.id[:8],
            s.tool,
            s.project_name,
            s.model or "-",
            str(s.message_count),
            s.started_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)


@app.command("show-paths")
def show_paths():
    """Show config and data paths."""
    from rich.console import Console

    from session_forge.config import config, config_path
    from session_forge.paths import _base_dir, db_path, logs_dir, service_ports_path
    from session_forge.service_runtime import read_service_state

    runtime = read_service_state()

    def _runtime_port(name: str) -> str:
        rec = runtime.get(name, {})
        port = rec.get("port")
        return str(port) if isinstance(port, int) else "-"

    console = Console()
    console.print(f"[bold]Config:[/bold]    {config_path()}")
    console.print(f"[bold]Base dir:[/bold]  {_base_dir()}")
    console.print(f"[bold]Database:[/bold]  {db_path()}")
    console.print(f"[bold]Projects:[/bold]  {_base_dir() / 'projects'}")
    console.print(f"[bold]Logs:[/bold]      {logs_dir()}")
    console.print(f"[bold]State file:[/bold] {service_ports_path()}")
    console.print(
        f"[bold]Proxy:[/bold]     {config().proxy.host}:{config().proxy.port}"
        f" (active: {_runtime_port('proxy')})"
    )
    console.print(
        f"[bold]MCP:[/bold]       {config().mcp_server.url}"
        f" (active: {_runtime_port('mcp_server')})"
    )
    console.print(
        f"[bold]Llama:[/bold]     {config().llama.server_url} ({config().llama.model_name})"
        f" (active: {_runtime_port('llama')})"
    )


@app.command("edit-config")
def edit_config():
    """Open config.yaml in $EDITOR."""
    import os
    import subprocess

    from session_forge.config import _ensure_config, config_path
    _ensure_config()
    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(config_path())])


@services_app.command("start")
def services_start():
    """Start/reuse all managed daemons."""
    from session_forge.service_runtime import ensure_all_daemons

    result = asyncio.run(ensure_all_daemons())
    _print_service_summary(result)


@services_app.command("status")
def services_status():
    """Show daemon status for all managed services."""
    from session_forge.service_runtime import service_status_snapshot

    result = asyncio.run(service_status_snapshot())
    _print_service_summary(result)


@services_app.command("stop")
def services_stop():
    """Stop all managed daemons."""
    from session_forge.service_runtime import stop_all_daemons

    result = stop_all_daemons()
    _print_service_summary(result)


@services_app.command("restart")
def services_restart():
    """Restart all managed daemons."""
    from session_forge.service_runtime import ensure_all_daemons, stop_all_daemons

    stop_result = stop_all_daemons()
    start_result = asyncio.run(ensure_all_daemons())
    typer.echo("Stopped:")
    _print_service_summary(stop_result)
    typer.echo("Started:")
    _print_service_summary(start_result)


app.add_typer(services_app, name="services")


if __name__ == "__main__":
    app()
