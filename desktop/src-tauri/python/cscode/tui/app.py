from __future__ import annotations

from cscode.core.config import load_config
from cscode.core.engine import Agent, AgentOptions
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
        input_widget.disabled = True

        output = self.query_one("#output-panel", RichLog)
        output.write(f"[bold green]You:[/] {user_input}")
        self._process_input(user_input)

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
