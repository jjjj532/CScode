from __future__ import annotations

import asyncio
from pathlib import Path

import click

from cscode import __version__
from cscode.core.config import load_config

if True:  # TYPE_CHECKING
    from cscode.app.agent import AgentV2


def _create_agent(mode: str | None = None) -> AgentV2:
    """Create AgentV2 from config (default backend).

    Args:
        mode: Optional agent mode (build, plan, subagent).
    """
    from cscode.app import create_agent_v2

    config = load_config()
    return create_agent_v2(config, mode=mode)


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="CScode")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """CScode — AI-powered coding assistant."""
    from cscode.utils.logging import setup_logging
    setup_logging("DEBUG")
    if ctx.invoked_subcommand is None:
        click.echo(f"CScode v{__version__}")
        click.echo("Run 'cs chat' to start an interactive session.")
        click.echo("Run 'cs --help' for all commands.")


@cli.command()
@click.option("-p", "--prompt", help="Single prompt to run (non-interactive)")
@click.option(
    "--mode",
    type=click.Choice(["build", "plan", "subagent"], case_sensitive=False),
    default="build",
    help="Agent mode (build, plan, subagent)",
)
def chat(prompt: str | None, mode: str) -> None:
    """Start an interactive chat session."""

    agent = _create_agent(mode=mode)

    if prompt:
        result = asyncio.run(agent.run(prompt))
        click.echo(result)
        return

    click.echo("CScode chat (v2)")
    click.echo("Type 'exit', 'quit', or Ctrl+C to end the session.")
    click.echo("")

    while True:
        try:
            user_input = click.prompt("> ", prompt_suffix=" ")
        except (EOFError, KeyboardInterrupt):
            click.echo("")
            break

        if user_input.lower() in ("exit", "quit", "/exit", "/quit", "/q"):
            break
        if not user_input.strip():
            continue

        result = asyncio.run(agent.run(user_input))
        click.echo(result)
        click.echo("")


@cli.group()
def agent() -> None:
    """Manage agent tabs and modes."""


@agent.command("list")
def agent_list() -> None:
    """List active agent tabs."""
    from cscode.core.agent.tab import TabManager

    mgr = TabManager()
    tabs = mgr.list_tabs()
    if not tabs:
        click.echo("No active tabs.")
        return
    active_tab = mgr.get_active()
    for tab in tabs:
        active = " (active)" if active_tab is not None and active_tab.id == tab.id else ""
        click.echo(f"  {tab.id}: {tab.title} [{tab.mode.value}]{active}")


@agent.command()
@click.argument("tab_id")
def switch(tab_id: str) -> None:
    """Switch to a different agent tab."""
    from cscode.core.agent.tab import TabManager

    mgr = TabManager()
    tab = mgr.switch_tab(tab_id)
    if tab is None:
        click.echo(f"Tab '{tab_id}' not found.")
        raise SystemExit(1)
    click.echo(f"Switched to tab: {tab.title} [{tab.mode.value}]")


@agent.command("mode")
@click.argument("new_mode", type=click.Choice(["build", "plan", "subagent"]))
def agent_mode(new_mode: str) -> None:
    """Set the active agent mode."""
    from cscode.core.agent.base import AgentMode

    mode = AgentMode(new_mode)
    click.echo(f"Agent mode set to: {mode.value}")


@cli.command()
def review() -> None:
    """Review code changes."""
    click.echo("Review mode not yet implemented.")


@cli.command()
def tui() -> None:
    """Start the terminal UI."""
    from cscode.tui.app import CScodeTUI

    app = CScodeTUI()
    app.run()


@cli.command()
@click.argument("key", required=False)
@click.argument("value", required=False)
def config(key: str | None, value: str | None) -> None:
    """Manage configuration."""

    cfg = load_config()
    if key and value:
        setattr(cfg, key.replace("-", "_"), value)
        config_path = Path.cwd() / ".cscode" / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.to_yaml(config_path)
        click.echo(f"Set {key}={value}")
    elif key:
        click.echo(getattr(cfg, key.replace("-", "_"), ""))
    else:
        click.echo("Current config:")
        for k, v in cfg.to_dict().items():
            click.echo(f"  {k}: {v}")


@cli.command()
@click.option("--port", default=8080, help="Port to listen on")
@click.option("--host", default="0.0.0.0", help="Host to bind to")
def server(port: int, host: str) -> None:
    """Start the web API server."""
    import uvicorn

    click.echo(f"Starting CScode server on http://{host}:{port}")
    uvicorn.run(
        "cscode.server.app:app",
        host=host,
        port=port,
        reload=False,
    )


@cli.command()
def web() -> None:
    """Open the web UI in a browser."""
    import webbrowser

    webbrowser.open("http://localhost:5173")
    click.echo("Opened web UI at http://localhost:5173")


@cli.command()
def desktop() -> None:
    """Launch the desktop app."""
    click.echo("Launching desktop app...")
    import subprocess

    subprocess.Popen(["open", "-a", "CScode"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@cli.group()
def migration() -> None:
    """Manage database migrations."""


@migration.command("list")
def migration_list() -> None:
    """List registered migrations with their status."""
    import asyncio

    from cscode.storage.db import Database, _get_migration_registry

    registry = _get_migration_registry()
    click.echo(f"{'Version':<8} {'Status':<12} Description")
    click.echo("-" * 60)

    async def _fetch() -> set[int]:
        db = Database()
        await db.init()
        applied = set()
        try:
            cursor = await db.conn.execute("SELECT version FROM schema_version")
            applied = {row[0] async for row in cursor}
        except Exception:
            pass
        finally:
            await db.close()
        return applied

    try:
        applied = asyncio.run(_fetch())
    except Exception as e:
        click.echo(f"Could not connect to database: {e}")
        applied = set()

    for m in registry.sorted():
        status = "applied" if m.version in applied else "pending"
        click.echo(f"{m.version:<8} {status:<12} {m.description}")


@migration.command("run")
@click.option("--target", default=None, type=int, help="Target version (default: latest)")
def migration_run(target: int | None) -> None:
    """Run pending migrations."""
    import asyncio

    from cscode.storage.db import Database, _get_migration_registry
    from cscode.storage.migration_runner import MigrationRunner

    async def _run() -> None:
        db = Database()
        await db.init()
        runner = MigrationRunner(db.conn, _get_migration_registry())
        applied = await runner.upgrade(target_version=target)
        if applied:
            click.echo(f"Applied migrations: {applied}")
        else:
            click.echo("No pending migrations.")
        await db.close()

    asyncio.run(_run())


@migration.command("rollback")
@click.argument("target", type=int, default=0)
def migration_rollback(target: int) -> None:
    """Roll back migrations to target version."""
    import asyncio

    from cscode.storage.db import Database, _get_migration_registry
    from cscode.storage.migration_runner import MigrationRunner

    async def _rollback() -> None:
        db = Database()
        await db.init()
        runner = MigrationRunner(db.conn, _get_migration_registry())
        rolled = await runner.downgrade(target)
        click.echo(f"Rolled back: {rolled}")
        await db.close()

    asyncio.run(_rollback())


def main() -> None:
    cli()
