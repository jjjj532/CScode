from __future__ import annotations

import asyncio
from pathlib import Path

import click

from cscode import __version__
from cscode.core.config import load_config

if True:  # TYPE_CHECKING
    from cscode.app.agent import AgentV2


def _create_agent() -> AgentV2:
    """Create AgentV2 from config (default backend)."""
    from cscode.app import create_agent_v2

    config = load_config()
    return create_agent_v2(config)


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
def chat(prompt: str | None) -> None:
    """Start an interactive chat session."""
    agent = _create_agent()

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

    async def _fetch():
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

    async def _run():
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

    async def _rollback():
        db = Database()
        await db.init()
        runner = MigrationRunner(db.conn, _get_migration_registry())
        rolled = await runner.downgrade(target)
        click.echo(f"Rolled back: {rolled}")
        await db.close()

    asyncio.run(_rollback())


def main() -> None:
    cli()
