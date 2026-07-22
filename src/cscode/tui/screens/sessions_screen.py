from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label

from cscode.core.tui_sessions import TuiSessionManager
from cscode.tui.screens.session_detail_screen import SessionDetailScreen


class SessionsScreen(Screen[None]):
    """Screen that lists TUI sessions in a DataTable with actions.

    Key bindings:
        - ``n`` — create a new session
        - ``d`` — delete the selected session
        - ``enter`` — open detail view for the selected session
        - ``escape`` — return without action
    """

    BINDINGS = [
        Binding("n", "create_session", "New", priority=True),
        Binding("d", "delete_session", "Delete", priority=True),
        Binding("escape", "app.pop_screen", "Back", priority=True),
    ]

    def __init__(self, manager: TuiSessionManager) -> None:
        super().__init__()
        self._manager = manager

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Label("Sessions", id="title-label", classes="screen-title"),
            Label("", id="count-label", classes="count"),
            DataTable(id="session-table", classes="session-table"),
            Label(
                "No sessions. Press [bold]N[/] to create one.",
                id="empty-label",
                classes="empty",
            ),
            id="main-content",
        )
        yield Footer()

    def on_mount(self) -> None:
        dt = self.query_one("#session-table", DataTable)
        dt.add_columns("ID", "Title", "Status", "Model")
        self._refresh_table()

    def _refresh_table(self) -> None:
        sessions = self._manager.list()
        active = self._manager.get_active()
        dt = self.query_one("#session-table", DataTable)
        empty_label = self.query_one("#empty-label", Label)
        count_label = self.query_one("#count-label", Label)

        if not sessions:
            dt.add_class("hidden")
            empty_label.remove_class("hidden")
            count_label.update("0 sessions")
            return

        dt.remove_class("hidden")
        empty_label.add_class("hidden")
        count_label.update(f"{len(sessions)} session{'s' if len(sessions) != 1 else ''}")

        dt.clear()
        for s in sessions:
            label = s.id[:8]
            is_active = active is not None and active.id == s.id
            title = f"{s.title} {'★' if is_active else ''}"
            dt.add_row(label, title, s.status, s.model)
            if is_active:
                dt.move_cursor(row=dt.row_count - 1)

    def action_create_session(self) -> None:
        self._manager.create()
        self._refresh_table()

    def action_delete_session(self) -> None:
        dt = self.query_one("#session-table", DataTable)
        if dt.cursor_row is None:
            return
        sessions = self._manager.list()
        if dt.cursor_row < len(sessions):
            self._manager.remove(sessions[dt.cursor_row].id)
            self._refresh_table()

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        sessions = self._manager.list()
        if event.cursor_row is not None and event.cursor_row < len(sessions):
            session = sessions[event.cursor_row]
            self._manager.set_active(session.id)
            self.app.push_screen(SessionDetailScreen(
                manager=self._manager,
                session_id=session.id,
            ))
