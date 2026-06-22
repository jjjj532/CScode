from __future__ import annotations

import asyncio
from pathlib import Path

import click

from cscode import __version__
from cscode.core.config import load_config
from cscode.core.engine import Agent, AgentOptions
from cscode.core.session_manager import Session, SessionManager
from cscode.tools.base import ToolRegistry


def _create_agent() -> Agent:
    config = load_config()
    from cscode.providers import create_provider

    provider = create_provider(config)
    registry = _default_registry()

    return Agent(
        config=config,
        provider=provider,
        registry=registry,
        options=AgentOptions(
            system_prompt="You are CScode, an AI-powered coding assistant. "
            "You help users write, review, and debug code. "
            "You have access to tools for reading, writing, and editing files, "
            "running shell commands, and searching codebases.",
        ),
    )


def _default_registry() -> ToolRegistry:
    from cscode.tools.bash import BashTool
    from cscode.tools.edit import EditTool
    from cscode.tools.glob import GlobTool
    from cscode.tools.grep import GrepTool
    from cscode.tools.ls import LsTool
    from cscode.tools.read import ReadTool
    from cscode.tools.write import WriteTool

    registry = ToolRegistry()
    registry.register(ReadTool())
    registry.register(WriteTool())
    registry.register(EditTool())
    registry.register(BashTool())
    registry.register(GrepTool())
    registry.register(GlobTool())
    registry.register(LsTool())
    return registry


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="CScode")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """CScode — AI-powered coding assistant."""
    if ctx.invoked_subcommand is None:
        click.echo(f"CScode v{__version__}")
        click.echo("Run 'cs chat' to start an interactive session.")
        click.echo("Run 'cs --help' for all commands.")


@cli.command()
@click.option("-p", "--prompt", help="Single prompt to run (non-interactive)")
@click.option("-m", "--model", help="Model to use")
def chat(prompt: str | None, model: str | None) -> None:
    """Start an interactive chat session."""
    agent = _create_agent()
    if model:
        agent.config.model = model

    if prompt:
        result = asyncio.run(agent.run(prompt))
        click.echo(result)
        return

    click.echo(f"CScode chat ({agent.provider.model})")
    click.echo("Type 'exit' or 'quit' to end the session.")
    click.echo("Type '/help' for commands.")
    click.echo("")

    while True:
        try:
            user_input = click.prompt("> ", prompt_suffix=" ")
        except (EOFError, KeyboardInterrupt):
            click.echo("")
            break

        if user_input.lower() in ("exit", "quit", "/exit", "/quit", "/q"):
            break
        if user_input.lower() in ("/help", "/h"):
            _show_help()
            continue
        if not user_input.strip():
            continue

        manager = _get_session_manager()

        if user_input.startswith("/sessions") or user_input == "/s":
            sessions = manager.list()
            active = manager.get_active()
            if not sessions:
                click.echo("No sessions.")
            else:
                for s in sessions:
                    marker = " *" if active and active.id == s.id else ""
                    click.echo(f"{s.id[:8]} - {s.title}{marker}")
            continue

        if user_input.startswith("/new") or user_input == "/n":
            s = manager.create()
            click.echo(f"Created new session: {s.id}")
            continue

        if user_input.startswith("/switch ") or user_input.startswith("/use "):
            target_id = user_input.split()[1]
            if manager.set_active(target_id):
                click.echo(f"Switched to: {target_id}")
            else:
                click.echo(f"Session not found: {target_id}")
            continue

        if user_input.startswith("/kill ") or user_input.startswith("/delete ") or user_input.startswith("/kill"):
            parts = user_input.split()
            if len(parts) > 1:
                target_id = parts[1]
            else:
                active = manager.get_active()
                if active:
                    target_id = active.id
                else:
                    click.echo("No active session to kill")
                    continue

            if manager.remove(target_id):
                click.echo(f"Session terminated: {target_id}")
            else:
                click.echo(f"Session not found: {target_id}")
            continue

        result = asyncio.run(agent.run(user_input))
        click.echo(result)
        click.echo("")


def _show_help() -> None:
    click.echo("Commands:")
    click.echo("  exit, quit, /q  End the session")
    click.echo("  /help, /h       Show this help")
    click.echo("  /sessions, /s   List all sessions")
    click.echo("  /new, /n        Create new session")
    click.echo("  /switch <id>    Switch to session")
    click.echo("  /use <id>       Switch to session")
    click.echo("  /kill [id]      Kill session (default: active)")


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

    click.echo(f"Starting CScode API server on {host}:{port}...")
    uvicorn.run("cscode.server.app:app", host=host, port=port, reload=False)


@cli.command()
@click.option("--port", default=8080, help="Port to listen on")
@click.option("--host", default="0.0.0.0", help="Host to bind to")
def web(port: int, host: str) -> None:
    """Start the web UI (API server + static files)."""
    import uvicorn

    click.echo(f"Starting CScode Web UI on {host}:{port}...")
    uvicorn.run("cscode.server.app:app", host=host, port=port, reload=False)


@cli.command()
@click.option("--dev", is_flag=True, help="Start in development mode with hot-reload")
def desktop(dev: bool) -> None:
    """Launch the desktop application."""
    from cscode.desktop_cli import launch_desktop

    launch_desktop(dev=dev)


def main() -> None:
    cli()


_session_manager: SessionManager | None = None


def _get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        async def persist_create(session: Session) -> None:
            from cscode.storage.session import get_session_store  # type: ignore[attr-defined]
            store = get_session_store()
            if store:
                await store.create(
                    title=session.title,
                    provider=session.provider,
                    model=session.model,
                    session_id=session.id,
                )

        async def persist_delete(session_id: str) -> None:
            from cscode.storage.session import get_session_store  # type: ignore[attr-defined]
            store = get_session_store()
            if store:
                await store.delete(session_id)

        def sync_create(session: Session) -> None:
            try:
                asyncio.run(persist_create(session))
            except Exception:
                pass

        def sync_delete(session_id: str) -> None:
            try:
                asyncio.run(persist_delete(session_id))
            except Exception:
                pass

        _session_manager = SessionManager(on_create=sync_create, on_delete=sync_delete)
    return _session_manager


@cli.group()
def session() -> None:
    """Manage sessions."""
    pass


@session.command("list")
def session_list() -> None:
    """List all sessions."""
    manager = _get_session_manager()
    sessions = manager.list()
    active = manager.get_active()

    if not sessions:
        click.echo("No sessions.")
        return

    for s in sessions:
        marker = " *" if active and active.id == s.id else ""
        click.echo(f"{s.id[:8]} - {s.title} ({s.status.value}){marker}")


@session.command("new")
@click.option("--name", default="", help="Session name")
@click.option("--provider", default="openai", help="LLM provider")
@click.option("--model", default="gpt-4o", help="Model name")
def session_new(name: str, provider: str, model: str) -> None:
    """Create a new session."""
    manager = _get_session_manager()
    s = manager.create(title=name, provider=provider, model=model)
    click.echo(f"Created session: {s.id}")
    click.echo(f"Title: {s.title}")
    click.echo(f"Provider: {s.provider}/{s.model}")


@session.command("use")
@click.argument("session_id")
def session_use(session_id: str) -> None:
    """Switch to a session."""
    manager = _get_session_manager()
    if manager.set_active(session_id):
        s = manager.get(session_id)
        assert s is not None
        click.echo(f"Switched to: {s.title}")
    else:
        click.echo(f"Session not found: {session_id}", err=True)


@session.command("kill")
@click.argument("session_id")
def session_kill(session_id: str) -> None:
    """Terminate a session."""
    manager = _get_session_manager()
    if manager.remove(session_id):
        click.echo(f"Session terminated: {session_id}")
    else:
        click.echo(f"Session not found: {session_id}", err=True)
