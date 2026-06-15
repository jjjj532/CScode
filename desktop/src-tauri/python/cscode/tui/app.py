from __future__ import annotations

from cscode.core.config import load_config
from cscode.core.engine import Agent, AgentOptions
from cscode.core.session_manager import SessionManager
from cscode.providers import create_provider
from cscode.tools.base import ToolRegistry
from cscode.tools.bash import BashTool
from cscode.tools.edit import EditTool
from cscode.tools.glob import GlobTool
from cscode.tools.grep import GrepTool
from cscode.tools.ls import LsTool
from cscode.tools.read import ReadTool
from cscode.tools.write import WriteTool
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Footer, Header, Input, RichLog


def _default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ReadTool())
    registry.register(WriteTool())
    registry.register(EditTool())
    registry.register(BashTool())
    registry.register(GrepTool())
    registry.register(GlobTool())
    registry.register(LsTool())
    return registry


class CScodeTUI(App):
    TITLE = "CScode"
    SUB_TITLE = "AI-powered coding assistant"
    CSS = """
    Screen {
        layout: vertical;
    }
    #output-panel {
        height: 1fr;
        border: solid $primary;
        padding: 1;
    }
    #input-container {
        height: 3;
        dock: bottom;
        padding: 0 1;
    }
    Input {
        width: 100%;
    }
    .status {
        height: 1;
        text-style: italic;
        color: $text-muted;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        config = load_config()
        provider = create_provider(config)
        self._session_manager = SessionManager()
        self._agent = Agent(
            config=config,
            provider=provider,
            registry=_default_registry(),
            options=AgentOptions(
                system_prompt="You are CScode, an AI-powered coding assistant.",
            ),
        )

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="output-panel", highlight=True, markup=True)
        yield Container(
            Input(placeholder="Type your message here...", id="input-box"),
            id="input-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        output = self.query_one("#output-panel", RichLog)
        output.write("[bold cyan]CScode[/] AI coding assistant")
        output.write(f"Model: {self._agent.provider.model}")
        output.write("Type your message and press Enter.")
        output.write("")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        user_input = event.value.strip()
        if not user_input:
            return

        input_widget = self.query_one("#input-box", Input)
        input_widget.value = ""

        output = self.query_one("#output-panel", RichLog)
        output.write(f"[bold green]You:[/] {user_input}")

        if self._handle_session_command(user_input, output):
            return

        input_widget.disabled = True
        self._process_input(user_input)

    def _handle_session_command(self, user_input: str, output: RichLog) -> bool:
        """Handle session management commands. Returns True if command was handled."""
        parts = user_input.split()

        if parts[0] in ("/sessions", "/s"):
            sessions = self._session_manager.list()
            active = self._session_manager.get_active()
            if not sessions:
                output.write("[dim]No sessions.[/dim]")
            else:
                for s in sessions:
                    marker = " [bold cyan]*[/bold cyan]" if active and active.id == s.id else ""
                    output.write(f"[dim]{s.id[:8]}[/dim] - {s.title}{marker}")
            return True

        if parts[0] in ("/new", "/n"):
            s = self._session_manager.create()
            output.write(f"[green]Created new session:[/] {s.id}")
            return True

        if parts[0] == "/switch" and len(parts) > 1:
            target_id = parts[1]
            if self._session_manager.set_active(target_id):
                output.write(f"[green]Switched to:[/] {target_id}")
            else:
                output.write(f"[red]Session not found:[/] {target_id}")
            return True

        if parts[0] in ("/kill", "/delete") and len(parts) > 1:
            target_id = parts[1]
            if self._session_manager.remove(target_id):
                output.write(f"[green]Session terminated:[/] {target_id}")
            else:
                output.write(f"[red]Session not found:[/] {target_id}")
            return True

        return False

    @work(thread=False)
    async def _process_input(self, user_input: str) -> None:
        output = self.query_one("#output-panel", RichLog)
        output.write("[bold yellow]CScode:[/] ")
        try:
            response = await self._agent.run(user_input)
            output.write(response)
        except Exception as e:
            output.write(f"[bold red]Error:[/] {e}")
        output.write("")
        self.query_one("#input-box", Input).disabled = False
        self.query_one("#input-box", Input).focus()
