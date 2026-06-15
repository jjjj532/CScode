from __future__ import annotations

import pytest
from cscode.tui.themes import Theme, apply_theme, PRESET_THEMES


class TestTheme:
    def test_create_theme(self) -> None:
        t = Theme(
            name="dark",
            primary="#00ff00",
            surface="#1a1a1a",
            text="#ffffff",
            muted="#888888",
            error="#ff0000",
            warning="#ffaa00",
            success="#00ff00",
        )
        assert t.name == "dark"
        assert t.primary == "#00ff00"

    def test_to_css_variables(self) -> None:
        t = Theme(
            name="test",
            primary="#ff0000",
            surface="#000000",
            text="#ffffff",
            muted="#888888",
            error="#ff0000",
            warning="#ffaa00",
            success="#00ff00",
        )
        css = t.to_css_variables()
        assert "$primary: #ff0000" in css
        assert "$surface: #000000" in css


class TestPresetThemes:
    def test_presets_exist(self) -> None:
        assert "catppuccin" in PRESET_THEMES
        assert "dracula" in PRESET_THEMES

    def test_preset_has_required_fields(self) -> None:
        for name, theme in PRESET_THEMES.items():
            assert theme.name == name
            assert theme.primary != ""
            assert theme.surface != ""

    def test_apply_theme_returns_css(self) -> None:
        css = apply_theme("catppuccin")
        assert css is not None
        assert "$primary" in css

    def test_apply_unknown_theme_returns_none(self) -> None:
        css = apply_theme("nonexistent")
        assert css is None
