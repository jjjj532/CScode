"""Tests for TUI CommandCompleter — Tab autocomplete for chat commands."""

from __future__ import annotations

from cscode.tui.autocomplete import CommandCompleter


def test_known_commands_includes_basic_commands() -> None:
    """The known commands list should include basic commands."""
    completer = CommandCompleter()
    commands = completer.known_commands()
    assert "/sessions" in commands
    assert "/new" in commands
    assert "/switch" in commands
    assert "/kill" in commands
    assert "/tab" in commands
    assert "/help" in commands
    assert "/quit" in commands


def test_known_commands_includes_aliases() -> None:
    """Aliases like /s, /n, /h, /q should be in the known commands."""
    completer = CommandCompleter()
    commands = completer.known_commands()
    assert "/s" in commands
    assert "/n" in commands
    assert "/h" in commands
    assert "/q" in commands
    assert "/exit" in commands
    assert "/delete" in commands


class TestFindMatches:
    def test_slash_returns_all_commands(self) -> None:
        """Typing just '/' should match all commands."""
        completer = CommandCompleter()
        matches = completer.find_matches("/")
        assert len(matches) > 5  # at least the basic commands
        assert "/sessions" in matches
        assert "/new" in matches

    def test_s_prefix_matches_sessions_and_switch(self) -> None:
        """Typing '/s' should match /sessions, /switch, /s."""
        completer = CommandCompleter()
        matches = completer.find_matches("/s")
        assert "/sessions" in matches
        assert "/switch" in matches
        assert "/s" in matches
        assert "/new" not in matches

    def test_n_prefix_matches_new(self) -> None:
        """Typing '/n' should match /new and /n."""
        completer = CommandCompleter()
        matches = completer.find_matches("/n")
        assert "/new" in matches
        assert "/n" in matches
        assert "/sessions" not in matches

    def test_sw_prefix_matches_only_switch(self) -> None:
        """Typing '/sw' should match only /switch."""
        completer = CommandCompleter()
        matches = completer.find_matches("/sw")
        assert matches == ["/switch"]

    def test_empty_prefix_returns_no_matches(self) -> None:
        """Empty string should return no matches."""
        completer = CommandCompleter()
        matches = completer.find_matches("")
        assert matches == []

    def test_non_slash_prefix_returns_no_matches(self) -> None:
        """Typing without leading slash should return no matches."""
        completer = CommandCompleter()
        matches = completer.find_matches("hello")
        assert matches == []

    def test_no_match_returns_empty_list(self) -> None:
        """No matching command returns empty list."""
        completer = CommandCompleter()
        matches = completer.find_matches("/zzzzz")
        assert matches == []

    def test_exact_match_includes_command(self) -> None:
        """Exact match should include the command."""
        completer = CommandCompleter()
        matches = completer.find_matches("/sessions")
        assert "/sessions" in matches

    def test_tab_prefix_matches_tab_commands(self) -> None:
        """Typing '/tab' should match /tab."""
        completer = CommandCompleter()
        matches = completer.find_matches("/tab")
        assert "/tab" in matches


class TestCycle:
    def test_next_match_returns_first_match(self) -> None:
        """First next_match after find_matches returns first match."""
        completer = CommandCompleter()
        completer.find_matches("/s")
        match = completer.next_match()
        assert match is not None
        assert match.startswith("/s")

    def test_next_match_cycles_through_matches(self) -> None:
        """Repeated next_match should cycle through all matches."""
        completer = CommandCompleter()
        completer.find_matches("/s")
        first = completer.next_match()
        second = completer.next_match()
        third = completer.next_match()
        assert first is not None
        assert second is not None
        assert third is not None
        # Must have at least 3 matches for /s
        assert len({first, second, third}) >= 2

    def test_next_match_wraps_around(self) -> None:
        """After last match, next_match wraps to first."""
        completer = CommandCompleter()
        completer.find_matches("/sw")
        first = completer.next_match()
        second = completer.next_match()
        # Only one match (/switch), second should wrap back
        assert first == "/switch"
        assert second == "/switch"

    def test_no_matches_returns_none(self) -> None:
        """next_match with no matches returns None."""
        completer = CommandCompleter()
        completer.find_matches("hello")
        assert completer.next_match() is None

    def test_reset_clears_state(self) -> None:
        """Reset should clear current match index."""
        completer = CommandCompleter()
        completer.find_matches("/s")
        completer.next_match()
        completer.reset()
        # After reset, should start from first again
        matches = completer.find_matches("/s")
        assert len(matches) > 0

    def test_find_matches_resets_cycle(self) -> None:
        """Calling find_matches again resets the cycle position."""
        completer = CommandCompleter()
        completer.find_matches("/s")
        completer.next_match()
        # Different prefix resets state
        matches = completer.find_matches("/n")
        assert "/new" in matches
        assert "/sessions" not in matches
