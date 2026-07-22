from __future__ import annotations

import time

from textual.app import ComposeResult, ScreenStackError
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, RichLog

from cscode.core.tui_sessions import TuiSessionManager


class SessionDetailScreen(Screen[None]):
    """Screen that shows full details and messages for a TUI session.

    Key bindings:
        - ``escape`` — return to previous screen
        - ``d`` — delete this session
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", priority=True),
        Binding("d", "delete_session", "Delete", priority=True),
    ]

    def __init__(self, manager: TuiSessionManager, session_id: str) -> None:
        super().__init__()
        self._manager = manager
        self._session_id = session_id

    def compose(self) -> ComposeResult:
        yield Header()
        yield ScrollableContainer(
            # Title + active indicator
            Horizontal(
                Label("", id="detail-title", classes="detail-title"),
                Label("", id="detail-active-indicator", classes="active-indicator hidden"),
                classes="detail-header-row",
            ),
            # Session ID
            Label("", id="detail-id", classes="detail-meta"),
            # Provider + Model
            Label("", id="detail-provider-model", classes="detail-meta"),
            # Status + timestamps
            Label("", id="detail-status", classes="detail-meta"),
            # Separator
            Label("─" * 60, id="detail-separator", classes="separator"),
            # Messages area
            RichLog(id="detail-messages", highlight=True, markup=True, classes="hidden"),
            Label("No messages.", id="detail-empty-label", classes="empty"),
            id="detail-scroll",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._populate()

    def _populate(self) -> None:
        session = self._manager.get(self._session_id)
        if session is None:
            return

        # Title
        title_label = self.query_one("#detail-title", Label)
        title_label.update(session.title)

        # Active indicator
        active_label = self.query_one("#detail-active-indicator", Label)
        active_session = self._manager.get_active()
        if active_session is not None and active_session.id == session.id:
            active_label.remove_class("hidden")
            active_label.update("★ Active")
        else:
            active_label.add_class("hidden")

        # ID
        id_label = self.query_one("#detail-id", Label)
        id_label.update(f"ID: {session.id}")

        # Provider / Model
        pm_label = self.query_one("#detail-provider-model", Label)
        pm_label.update(f"{session.provider} · {session.model}")

        # Status
        status_label = self.query_one("#detail-status", Label)
        created = time.strftime(
            "%Y-%m-%d %H:%M",
            time.localtime(session.created_at),
        )
        status_label.update(
            f"Status: {session.status}  |  Created: {created}"
        )

        # Messages
        rlog = self.query_one("#detail-messages", RichLog)
        empty_label = self.query_one("#detail-empty-label", Label)

        if not session.messages:
            rlog.add_class("hidden")
            empty_label.remove_class("hidden")
            return

        rlog.remove_class("hidden")
        empty_label.add_class("hidden")
        for msg in session.messages:
            role_tag = self._role_tag(msg.role)
            rlog.write(f"{role_tag} {msg.content}")

    @staticmethod
    def _role_tag(role: str) -> str:
        tags = {
            "user": "[bold green]You:[/]",
            "assistant": "[bold cyan]AI:[/]",
            "system": "[bold yellow]System:[/]",
        }
        default = f"[bold]{role}:[/]"
        return tags.get(role, default)

    def action_delete_session(self) -> None:
        """Delete this session and pop back."""
        self._manager.remove(self._session_id)
        try:
            self.app.pop_screen()
        except ScreenStackError:
            pass
