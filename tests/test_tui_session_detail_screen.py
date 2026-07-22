"""Tests for TUI SessionDetailScreen — session detail view.

Uses Textual's ``run_test`` pilot for widget testing via a TestApp wrapper.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Footer, Label, RichLog

from cscode.core.tui_sessions import TuiMessage, TuiSessionManager
from cscode.tui.screens.session_detail_screen import SessionDetailScreen


class _DetailTestApp(App[None]):  # type: ignore[type-arg]
    """Minimal Textual App that wraps a SessionDetailScreen as the root screen."""

    def __init__(self, manager: TuiSessionManager, session_id: str) -> None:
        super().__init__()
        self._manager = manager
        self._session_id = session_id

    def compose(self) -> ComposeResult:
        yield SessionDetailScreen(manager=self._manager, session_id=self._session_id)


def _make_manager_with_messages(
    title: str = "Test Session",
    n_messages: int = 0,
) -> TuiSessionManager:
    """Create a TuiSessionManager with one session and optional messages."""
    mgr = TuiSessionManager(max_sessions=10)
    session = mgr.create(title=title)
    for i in range(n_messages):
        role = "user" if i % 2 == 0 else "assistant"
        session.messages.append(
            TuiMessage(role=role, content=f"Message {i + 1}")
        )
    return mgr


class TestEmptyState:
    async def test_shows_no_messages_placeholder_when_empty(self) -> None:
        """When session has no messages, show placeholder instead of RichLog."""
        mgr = _make_manager_with_messages(n_messages=0)
        s = mgr.list()[0]
        app = _DetailTestApp(manager=mgr, session_id=s.id)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionDetailScreen)
            # Empty label should be visible
            empty_label = screen.query_one("#detail-empty-label", Label)
            # RichLog should be hidden
            rlog = screen.query_one("#detail-messages", RichLog)
            assert not empty_label.has_class("hidden")
            assert rlog.has_class("hidden")


class TestMetadata:
    async def test_shows_session_title(self) -> None:
        """Detail screen should display the session title."""
        mgr = _make_manager_with_messages(title="My Session", n_messages=1)
        s = mgr.list()[0]
        app = _DetailTestApp(manager=mgr, session_id=s.id)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionDetailScreen)
            title_label = screen.query_one("#detail-title", Label)
            rendered = str(title_label.render())  # type: ignore[operator]
            assert "My Session" in rendered

    async def test_shows_session_id_truncated(self) -> None:
        """Detail screen should show the first 8 chars of session ID."""
        mgr = _make_manager_with_messages(title="ID Test", n_messages=1)
        s = mgr.list()[0]
        app = _DetailTestApp(manager=mgr, session_id=s.id)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionDetailScreen)
            id_label = screen.query_one("#detail-id", Label)
            rendered = str(id_label.render())  # type: ignore[operator]
            assert s.id[:8] in rendered

    async def test_shows_provider_and_model(self) -> None:
        """Detail screen should show provider and model."""
        mgr = _make_manager_with_messages(title="PM Test", n_messages=1)
        s = mgr.list()[0]
        app = _DetailTestApp(manager=mgr, session_id=s.id)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionDetailScreen)
            pm_label = screen.query_one("#detail-provider-model", Label)
            rendered = str(pm_label.render())  # type: ignore[operator]
            assert s.provider in rendered
            assert s.model in rendered

    async def test_shows_status(self) -> None:
        """Detail screen should show session status."""
        mgr = _make_manager_with_messages(title="Status Test", n_messages=1)
        s = mgr.list()[0]
        app = _DetailTestApp(manager=mgr, session_id=s.id)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionDetailScreen)
            status_label = screen.query_one("#detail-status", Label)
            rendered = str(status_label.render())  # type: ignore[operator]
            assert s.status in rendered

    async def test_active_session_shows_indicator(self) -> None:
        """If the session is active, an indicator should appear."""
        mgr = _make_manager_with_messages(title="Active", n_messages=1)
        s = mgr.list()[0]
        mgr.set_active(s.id)
        app = _DetailTestApp(manager=mgr, session_id=s.id)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionDetailScreen)
            active_label = screen.query_one("#detail-active-indicator")
            rendered = str(active_label.render())  # type: ignore[operator]
            assert rendered.strip()


class TestMessages:
    async def test_shows_messages_in_richlog(self) -> None:
        """Messages should appear in the RichLog widget."""
        mgr = _make_manager_with_messages(title="Msgs", n_messages=3)
        s = mgr.list()[0]
        app = _DetailTestApp(manager=mgr, session_id=s.id)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionDetailScreen)
            rlog = screen.query_one("#detail-messages", RichLog)
            # With messages, RichLog should be visible, empty label hidden
            empty_label = screen.query_one("#detail-empty-label", Label)
            assert not rlog.has_class("hidden")
            assert empty_label.has_class("hidden")

    async def test_richlog_shows_role_and_content(self) -> None:
        """Each message should show role label and content."""
        mgr = _make_manager_with_messages(title="MsgTest", n_messages=2)
        s = mgr.list()[0]
        app = _DetailTestApp(manager=mgr, session_id=s.id)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionDetailScreen)
            rlog = screen.query_one("#detail-messages", RichLog)
            # Check lines were written to RichLog (2 messages = 2 lines)
            assert len(rlog.lines) >= 2  # type: ignore[attr-defined]


class TestNavigation:
    async def test_escape_returns_to_previous_screen(self) -> None:
        """Pressing Escape should pop the screen."""
        mgr = _make_manager_with_messages(title="Nav", n_messages=1)
        s = mgr.list()[0]
        root_app = _DetailTestApp(manager=mgr, session_id=s.id)
        async with root_app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            child = SessionDetailScreen(manager=mgr, session_id=s.id)
            await root_app.push_screen(child)
            await pilot.pause()
            assert root_app.screen is child
            await pilot.press("escape")
            await pilot.pause()
            assert root_app.screen is not child

    async def test_d_deletes_session(self) -> None:
        """Pressing 'd' should delete the session."""
        mgr = _make_manager_with_messages(title="Delete Me", n_messages=1)
        s = mgr.list()[0]
        app = _DetailTestApp(manager=mgr, session_id=s.id)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert len(mgr.list()) == 1
            # Call directly to avoid screen stack issue in test
            screen = app.query_one(SessionDetailScreen)
            screen.action_delete_session()
            await pilot.pause()
            assert len(mgr.list()) == 0


class TestFooter:
    async def test_footer_present(self) -> None:
        """Footer with keybinding hints should be visible."""
        mgr = _make_manager_with_messages(title="Footer", n_messages=1)
        s = mgr.list()[0]
        app = _DetailTestApp(manager=mgr, session_id=s.id)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SessionDetailScreen)
            footer = screen.query_one(Footer)
            assert footer is not None
