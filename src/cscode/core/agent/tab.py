"""TabManager — multi-tab session management."""

from __future__ import annotations

import time

from cscode.core.agent.base import AgentMode, AgentTab


class TabManager:
    """Manages multiple agent tabs for multi-session workflows.

    Each tab wraps a session_id and mode. Only one tab is active at a time.
    Supports a configurable maximum number of concurrent tabs.
    """

    def __init__(self, max_tabs: int = 10) -> None:
        self._tabs: dict[str, AgentTab] = {}
        self._active_id: str | None = None
        self._max_tabs = max_tabs
        self._counter = 0

    def create_tab(
        self,
        mode: AgentMode = AgentMode.BUILD,
        title: str = "",
    ) -> AgentTab:
        """Create a new agent tab.

        Args:
            mode: Agent execution mode.
            title: Display title. Auto-generated if empty.

        Returns:
            The newly created AgentTab.

        Raises:
            ValueError: If the maximum number of tabs has been reached.
        """
        if len(self._tabs) >= self._max_tabs:
            raise ValueError(
                f"Maximum tabs ({self._max_tabs}) reached"
            )

        self._counter += 1
        tab_id = f"tab_{self._counter}"
        session_id = f"sess_{time.time_ns()}"

        if not title:
            title = f"Tab {self._counter}"

        tab = AgentTab(
            id=tab_id,
            mode=mode,
            session_id=session_id,
            title=title,
            created_at=time.time(),
        )
        self._tabs[tab_id] = tab
        self._active_id = tab_id
        return tab

    def switch_tab(self, tab_id: str) -> AgentTab | None:
        """Switch the active tab.

        Args:
            tab_id: ID of the tab to switch to.

        Returns:
            The tab if found, or None.
        """
        if tab_id not in self._tabs:
            return None
        self._active_id = tab_id
        return self._tabs[tab_id]

    def close_tab(self, tab_id: str) -> AgentTab | None:
        """Close and remove a tab.

        If the closed tab was active, the next available tab becomes active.
        If no tabs remain, active is set to None.

        Args:
            tab_id: ID of the tab to close.

        Returns:
            The closed tab if found, or None.
        """
        tab = self._tabs.pop(tab_id, None)
        if tab is None:
            return None

        if self._active_id == tab_id:
            remaining = list(self._tabs.keys())
            self._active_id = remaining[0] if remaining else None

        return tab

    def list_tabs(self) -> list[AgentTab]:
        """Return all tabs in creation order."""
        return list(self._tabs.values())

    def get_active(self) -> AgentTab | None:
        """Return the currently active tab, or None."""
        if self._active_id is None:
            return None
        return self._tabs.get(self._active_id)
