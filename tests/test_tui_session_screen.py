"""Tests for TUI SessionsScreen — session list view.

Uses Textual's ``run_test`` pilot for widget testing via a TestApp wrapper.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Label

from cscode.core.tui_sessions import TuiSessionManager
from cscode.tui.screens.sessions_screen import SessionsScreen


class _SessionTestApp(App[None]):  # type: ignore[type-arg]
    """Minimal Textual App that wraps a SessionsScreen as the root screen."""

    def __init__(self, manager: TuiSessionManager) -> None:
        super().__init__()
        self._manager = manager

    def compose(self) -> ComposeResult:
        yield SessionsScreen(manager=self._manager)


def _make_manager(*titles: str) -> TuiSessionManager:
    """Create a TuiSessionManager pre-populated with sessions."""
    mgr = TuiSessionManager(max_sessions=10)
    for t in titles:
        mgr.create(title=t)
    return mgr


class TestEmptyState:
    async def test_shows_empty_label_when_no_sessions(self) -> None:
        """Screen should display an empty-state message when no sessions exist."""
        mgr = TuiSessionManager(max_sessions=10)
        app = _SessionTestApp(manager=mgr)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionsScreen)
            label = screen.query_one("#empty-label", Label)
            assert not label.has_class("hidden")

    async def test_datatable_exists_but_hidden_when_empty(self) -> None:
        """DataTable exists in DOM but has 'hidden' class when no sessions."""
        mgr = TuiSessionManager(max_sessions=10)
        app = _SessionTestApp(manager=mgr)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionsScreen)
            dt = screen.query_one(DataTable)
            assert dt.has_class("hidden")
            empty = screen.query_one("#empty-label", Label)
            assert not empty.has_class("hidden")

    async def test_datatable_unhidden_after_action_create(self) -> None:
        """After action_create_session, DataTable visible and empty label hidden."""
        mgr = TuiSessionManager(max_sessions=10)
        app = _SessionTestApp(manager=mgr)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionsScreen)
            dt = screen.query_one(DataTable)
            assert dt.has_class("hidden")
            screen.action_create_session()
            await pilot.pause()
            assert not dt.has_class("hidden")
            assert dt.row_count == 1


class TestListView:
    async def test_datatable_renders_with_sessions(self) -> None:
        """DataTable should have one row per session."""
        mgr = _make_manager("Alpha", "Beta")
        app = _SessionTestApp(manager=mgr)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionsScreen)
            dt = screen.query_one(DataTable)
            assert dt.row_count == 2

    async def test_datatable_columns_include_expected_labels(self) -> None:
        """Columns should include ID, Title, Status, Model."""
        mgr = _make_manager("Test")
        app = _SessionTestApp(manager=mgr)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionsScreen)
            dt = screen.query_one(DataTable)
            labels = [str(c.label or "") for c in dt.columns.values()]
            assert any("ID" in lbl for lbl in labels)
            assert any("Title" in lbl for lbl in labels)
            assert any("Status" in lbl for lbl in labels)

    async def test_session_count_label(self) -> None:
        """A label should display the session count."""
        mgr = _make_manager("A", "B")
        app = _SessionTestApp(manager=mgr)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionsScreen)
            count_label = screen.query_one("#count-label", Label)
            assert "2" in str(count_label.render())  # type: ignore[operator]

    async def test_footer_present(self) -> None:
        """Footer with keybinding hints should be visible."""
        mgr = TuiSessionManager(max_sessions=10)
        app = _SessionTestApp(manager=mgr)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionsScreen)
            footer = screen.query_one(Footer)
            assert footer is not None


class TestNavigation:

    async def test_action_create_session(self) -> None:
        """action_create_session should create a new session."""
        mgr = TuiSessionManager(max_sessions=10)
        app = _SessionTestApp(manager=mgr)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionsScreen)
            assert len(mgr.list()) == 0
            screen.action_create_session()
            assert len(mgr.list()) == 1

    async def test_action_delete_session_resets_to_empty(self) -> None:
        """Deleting the last session should hide the DataTable."""
        mgr = _make_manager("Delete Me")
        app = _SessionTestApp(manager=mgr)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionsScreen)
            assert len(mgr.list()) == 1
            screen.action_delete_session()
            await pilot.pause()
            assert len(mgr.list()) == 0
            dt = screen.query_one(DataTable)
            assert dt.has_class("hidden")

    async def test_select_session_activates_it(self) -> None:
        """Selecting a row should activate that session."""
        mgr = _make_manager("One", "Two")
        app = _SessionTestApp(manager=mgr)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionsScreen)
            dt = screen.query_one(DataTable)
            dt.focus()
            await pilot.press("down", "enter")
            await pilot.pause()
            active = mgr.get_active()
            assert active is not None
            assert active.title == "Two"

    async def test_escape_pops_screen(self) -> None:
        """Pressing Escape should pop the screen from stack."""
        mgr = TuiSessionManager(max_sessions=10)
        app = _SessionTestApp(manager=mgr)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            root_screen = app.screen
            child = SessionsScreen(manager=mgr)
            await app.push_screen(child)
            await pilot.pause()
            assert app.screen is child
            await pilot.press("escape")
            await pilot.pause()
            assert app.screen is root_screen
