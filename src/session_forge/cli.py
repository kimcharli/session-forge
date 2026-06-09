"""Typer CLI — proxy, mcp-server, analyze, list-sessions, show-paths commands."""

import asyncio

import typer
import uvicorn

app = typer.Typer(name="session-forge", help="AI session intercept, storage, and analysis.")


@app.command()
def proxy(
    port: int = typer.Option(None, help="Proxy listen port (default: from config)"),
    host: str = typer.Option(None, help="Proxy listen host (default: from config)"),
):
    """Start the HTTPS intercept proxy."""
    from session_forge.config import config
    from session_forge.proxy.app import app as proxy_app
    cfg = config().proxy
    host = host or cfg.host
    port = port or cfg.port
    typer.echo(f"Starting proxy on {host}:{port}")
    typer.echo(f"  Set ANTHROPIC_BASE_URL=http://{host}:{port} for Claude Code")
    uvicorn.run(proxy_app, host=host, port=port, log_level="info")


@app.command("mcp-server")
def mcp_server(
    port: int = typer.Option(None, help="MCP server listen port (default: from config)"),
    host: str = typer.Option(None, help="MCP server listen host (default: from config)"),
):
    """Start the MCP server (HTTP ingest + MCP tools)."""
    from session_forge.config import config
    from session_forge.mcp_server.server import http_app
    cfg = config().mcp_server
    host = host or cfg.host
    port = port or cfg.port
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
    from session_forge.paths import db_path, _base_dir, service_ports_path
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
    from session_forge.config import config_path, _ensure_config
    _ensure_config()
    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(config_path())])


if __name__ == "__main__":
    app()
