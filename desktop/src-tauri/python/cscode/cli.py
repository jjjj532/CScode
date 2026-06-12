from __future__ import annotations

import asyncio
from pathlib import Path

import click

from cscode import __version__
from cscode.core.config import load_config
from cscode.core.engine import Agent, AgentOptions
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

        result = asyncio.run(agent.run(user_input))
        click.echo(result)
        click.echo("")


def _show_help() -> None:
    click.echo("Commands:")
    click.echo("  exit, quit, /q  End the session")
    click.echo("  /help, /h       Show this help")


@cli.command()
def review() -> None:
    """Review code changes."""
    click.echo("Review mode not yet implemented.")


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
