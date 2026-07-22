from __future__ import annotations

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, Input, Label, RichLog

from cscode.app.factory import create_agent_v2
from cscode.core.agent.base import AgentMode, AgentTab
from cscode.core.agent.tab import TabManager
from cscode.core.config import load_config
from cscode.core.tui_sessions import TuiSessionManager
from cscode.tui.autocomplete import CommandCompleter
from cscode.tui.screens.sessions_screen import SessionsScreen
from cscode.tui.screens.settings_screen import SettingsScreen
from cscode.tui.themes import apply_theme


class CScodeTUI(App[None]):
    TITLE = "CScode"
    SUB_TITLE = "AI-powered coding assistant"

    BINDINGS = [
        Binding("f2", "show_sessions", "Sessions", priority=True),
        Binding("f3", "show_settings", "Settings", priority=True),
        Binding("tab", "autocomplete", "Complete", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        config = load_config()
        theme_css = apply_theme(config.theme) or apply_theme("catppuccin") or ""
        css = theme_css + """
        Screen { layout: vertical; }
        #output-panel {
            height: 1fr;
            border: solid $primary;
            padding: 1;
        }
        #input-container {
            height: 4;
            dock: bottom;
            padding: 0 1;
        }
        Input { width: 100%; }
        .status {
            height: 1;
            text-style: italic;
            color: $text-muted;
        }
        .autocomplete-hint {
            height: 1;
            color: $text-muted;
            text-style: italic;
        }
        """
        self.CSS = css  # type: ignore[misc]

        config.system_prompt = "You are CScode, an AI-powered coding assistant."
        self._agent = create_agent_v2(config)
        self._session_manager = TuiSessionManager()
        self._tab_manager = TabManager()
        self._completer = CommandCompleter()

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="output-panel", highlight=True, markup=True)
        yield Container(
            Input(placeholder="Type your message here...", id="input-box"),
            Label("", id="autocomplete-hint", classes="autocomplete-hint"),
            id="input-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        output = self.query_one("#output-panel", RichLog)
        output.write("[bold cyan]CScode[/] AI coding assistant")
        output.write(f"Model: {self._agent.llm_client.route.model}")
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

    def action_show_sessions(self) -> None:
        """Open the Sessions list screen."""
        self.push_screen(SessionsScreen(manager=self._session_manager))

    def action_show_settings(self) -> None:
        """Open the Settings screen."""
        # Import inline to avoid circular import at module level
        from cscode.core.config import load_config

        config = load_config()
        self.push_screen(SettingsScreen(config=config))

    def action_autocomplete(self) -> None:
        """Tab: cycle through command autocompletions."""
        input_box = self.query_one("#input-box", Input)
        if not input_box.has_focus or not input_box.value.startswith("/"):
            return

        prefix = input_box.value
        matches = self._completer.find_matches(prefix)
        if not matches:
            return

        completion = self._completer.next_match()
        if completion is not None and completion != prefix:
            input_box.value = completion
            input_box.cursor_position = len(completion)

        self._update_hint(matches)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update autocomplete hint as the user types."""
        val = event.value
        if val.startswith("/"):
            matches = self._completer.find_matches(val)
            self._update_hint(matches)
        else:
            self._completer.reset()
            self.query_one("#autocomplete-hint", Label).update("")

    def _update_hint(self, matches: list[str]) -> None:
        hint = self.query_one("#autocomplete-hint", Label)
        if not matches:
            hint.update("")
        elif len(matches) == 1:
            hint.update("")
        else:
            hint.update(f"  {'  '.join(matches)}")

    def _handle_session_command(self, user_input: str, output: RichLog) -> bool:
        """Handle session management commands. Returns True if command was handled."""
        parts = user_input.split()

        if parts[0] in ("/sessions", "/s"):
            sessions = self._session_manager.list()
            active_session = self._session_manager.get_active()
            if not sessions:
                output.write("[dim]No sessions.[/dim]")
            else:
                for s in sessions:
                    marker = " [bold cyan]*[/bold cyan]" if active_session and active_session.id == s.id else ""
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

        if parts[0] == "/tab":
            cmd = parts[1] if len(parts) > 1 else "list"
            if cmd == "list":
                tabs = self._tab_manager.list_tabs()
                active_tab: AgentTab | None = self._tab_manager.get_active()
                if not tabs:
                    output.write("[dim]No tabs.[/dim]")
                else:
                    for t in tabs:
                        marker = " [bold cyan]*[/]" if active_tab and t.id == active_tab.id else ""
                        output.write(f"[dim]{t.id}[/] [{t.mode.value}] - {t.title}{marker}")
                return True
            if cmd == "create" and len(parts) > 2:
                mode_str = parts[2].lower()
                mode = AgentMode.BUILD if mode_str == "build" else AgentMode.PLAN if mode_str == "plan" else AgentMode.SUBAGENT if mode_str == "subagent" else None
                if mode is None:
                    output.write(f"[red]Invalid mode: {mode_str} (use: build/plan/subagent)[/]")
                else:
                    tab = self._tab_manager.create_tab(mode=mode)
                    output.write(f"[green]Created tab:[/] {tab.id} [{tab.mode.value}]")
                return True
            if cmd == "switch" and len(parts) > 2:
                switched: AgentTab | None = self._tab_manager.switch_tab(parts[2])
                if switched:
                    output.write(f"[green]Switched to tab:[/] {switched.id} [{switched.mode.value}]")
                else:
                    output.write(f"[red]Tab not found:[/] {parts[2]}")
                return True
            if cmd == "close" and len(parts) > 2:
                closed: AgentTab | None = self._tab_manager.close_tab(parts[2])
                if closed:
                    output.write(f"[green]Closed tab:[/] {closed.id}")
                else:
                    output.write(f"[red]Tab not found:[/] {parts[2]}")
                return True
            output.write("[yellow]Usage:[/] /tab list|create <mode>|switch <id>|close <id>")
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
