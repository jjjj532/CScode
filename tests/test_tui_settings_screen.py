"""Tests for TUI SettingsScreen — config editor view.

Uses Textual's ``run_test`` pilot for widget testing via a TestApp wrapper.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Button, Footer, Input, Label

from cscode.core.config import Config
from cscode.tui.screens.settings_screen import SettingsScreen


class _SettingsTestApp(App[None]):
    """Minimal Textual App that wraps a SettingsScreen as the root screen."""

    def __init__(self, config: Config, save_callback=None) -> None:
        super().__init__()
        self._config = config
        self._save_callback = save_callback

    def compose(self) -> ComposeResult:
        yield SettingsScreen(config=self._config, save_callback=self._save_callback)


def demo_config() -> Config:
    return Config(
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        temperature=0.5,
        theme="dracula",
        system_prompt="You are a test assistant.",
        api_key="sk-test",
    )


class TestRender:

    async def test_title_and_footer_present(self) -> None:
        """Screen should have a title label and footer."""
        app = _SettingsTestApp(config=Config())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SettingsScreen)
            assert screen.query_one("#settings-title") is not None
            assert screen.query_one(Footer) is not None

    async def test_fields_populated_with_config_values(self) -> None:
        """Input fields should show current config values."""
        cfg = demo_config()
        app = _SettingsTestApp(config=cfg)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SettingsScreen)
            assert screen.query_one("#model-input", Input).value == "claude-sonnet-4-20250514"
            assert screen.query_one("#provider-input", Input).value == "anthropic"
            assert screen.query_one("#temperature-input", Input).value == "0.5"

    async def test_save_button_present(self) -> None:
        """Save button should be visible."""
        app = _SettingsTestApp(config=Config())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SettingsScreen)
            assert screen.query_one("#save-btn", Button) is not None

    async def test_theme_field_populated(self) -> None:
        """Theme input should show current theme."""
        cfg = Config(theme="monokai")
        app = _SettingsTestApp(config=cfg)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SettingsScreen)
            assert screen.query_one("#theme-input", Input).value == "monokai"

    async def test_system_prompt_field_populated(self) -> None:
        """System prompt input should show current prompt."""
        cfg = Config(system_prompt="Custom prompt")
        app = _SettingsTestApp(config=cfg)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SettingsScreen)
            assert screen.query_one("#prompt-input", Input).value == "Custom prompt"


class TestEdit:

    async def test_set_model_value_directly(self) -> None:
        """Setting Input.value should update the displayed value."""
        app = _SettingsTestApp(config=Config())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            inp = app.query_one("#model-input", Input)
            inp.value = "gpt-4o"
            await pilot.pause()
            assert inp.value == "gpt-4o"


class TestSave:

    async def test_save_calls_callback_with_model_value(self) -> None:
        """Save should pass the current Input.value to the callback."""
        saved_cfgs: list[Config] = []

        def on_save(cfg: Config) -> None:
            saved_cfgs.append(cfg)

        app = _SettingsTestApp(config=Config(model="gpt-4o"), save_callback=on_save)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            child = SettingsScreen(config=Config(model="gpt-4o"), save_callback=on_save)
            await app.push_screen(child)
            await pilot.pause()
            child.query_one("#model-input", Input).value = "gpt-4o-mini"
            child.action_save()
            await pilot.pause()
            assert len(saved_cfgs) == 1
            assert saved_cfgs[0].model == "gpt-4o-mini"

    async def test_save_uses_provider_value(self) -> None:
        """Save should pass the provider field to the callback."""
        saved_cfgs: list[Config] = []

        def on_save(cfg: Config) -> None:
            saved_cfgs.append(cfg)

        app = _SettingsTestApp(config=Config(provider="openai"), save_callback=on_save)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            child = SettingsScreen(config=Config(provider="openai"), save_callback=on_save)
            await app.push_screen(child)
            await pilot.pause()
            child.query_one("#provider-input", Input).value = "anthropic"
            child.action_save()
            assert saved_cfgs[0].provider == "anthropic"

    async def test_save_updates_temperature(self) -> None:
        """Save should pass the temperature field to the callback."""
        saved_cfgs: list[Config] = []

        def on_save(cfg: Config) -> None:
            saved_cfgs.append(cfg)

        app = _SettingsTestApp(config=Config(temperature=0.3), save_callback=on_save)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            child = SettingsScreen(config=Config(temperature=0.3), save_callback=on_save)
            await app.push_screen(child)
            await pilot.pause()
            child.query_one("#temperature-input", Input).value = "0.7"
            child.action_save()
            assert saved_cfgs[0].temperature == 0.7

    async def test_save_pops_screen(self) -> None:
        """Save should pop the screen when not root."""
        verify = {}

        def on_save(cfg: Config) -> None:
            verify["called"] = True

        app = _SettingsTestApp(config=Config(), save_callback=on_save)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            root_screen = app.screen
            child = SettingsScreen(config=Config(), save_callback=on_save)
            await app.push_screen(child)
            await pilot.pause()
            assert app.screen is child
            child.action_save()
            await pilot.pause()
            assert app.screen is root_screen
            assert verify.get("called")

    async def test_save_without_callback_does_not_crash(self) -> None:
        """Save should not crash when no callback set."""
        app = _SettingsTestApp(config=Config())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            child = SettingsScreen(config=Config())
            await app.push_screen(child)
            await pilot.pause()
            child.action_save()
            await pilot.pause()


class TestCancel:

    async def test_escape_pops_screen(self) -> None:
        """Escape should pop the screen."""
        app = _SettingsTestApp(config=Config())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            root_screen = app.screen
            child = SettingsScreen(config=Config())
            await app.push_screen(child)
            await pilot.pause()
            assert app.screen is child
            await pilot.press("escape")
            await pilot.pause()
            assert app.screen is root_screen

    async def test_cancel_button_pops_screen(self) -> None:
        """Cancel button should pop the screen."""
        app = _SettingsTestApp(config=Config())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            root_screen = app.screen
            child = SettingsScreen(config=Config())
            await app.push_screen(child)
            await pilot.pause()
            btn = child.query_one("#cancel-btn", Button)
            btn.focus()
            await pilot.press("enter")
            await pilot.pause()
            assert app.screen is root_screen


class TestValidation:

    async def test_empty_model_shows_error(self) -> None:
        """Empty model should show validation error label."""
        app = _SettingsTestApp(config=Config(model="gpt-4o"))
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SettingsScreen)
            screen.query_one("#model-input", Input).value = ""
            screen.action_save()
            await pilot.pause()
            err = screen.query_one("#validation-error", Label)
            assert err is not None
            assert not err.has_class("hidden")

    async def test_temperature_out_of_range_shows_error(self) -> None:
        """Temperature > 2.0 should show validation error."""
        cfg = Config(temperature=1.5)
        app = _SettingsTestApp(config=cfg)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SettingsScreen)
            screen.query_one("#temperature-input", Input).value = "3.0"
            screen.action_save()
            await pilot.pause()
            err = screen.query_one("#validation-error", Label)
            assert not err.has_class("hidden")

    async def test_invalid_temperature_string_shows_error(self) -> None:
        """Non-numeric temperature should show validation error."""
        app = _SettingsTestApp(config=Config(temperature=0.3))
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.query_one(SettingsScreen)
            screen.query_one("#temperature-input", Input).value = "hot"
            screen.action_save()
            await pilot.pause()
            err = screen.query_one("#validation-error", Label)
            assert not err.has_class("hidden")

    async def test_valid_input_hides_error(self) -> None:
        """After fixing validation error and saving, error should be hidden."""
        saved: list[Config] = []

        def on_save(cfg: Config) -> None:
            saved.append(cfg)

        app = _SettingsTestApp(config=Config(model="gpt-4o", temperature=1.0), save_callback=on_save)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            child = SettingsScreen(config=Config(model="gpt-4o", temperature=1.0), save_callback=on_save)
            await app.push_screen(child)
            await pilot.pause()
            child.query_one("#model-input", Input).value = ""
            child.action_save()
            await pilot.pause()
            err = child.query_one("#validation-error", Label)
            assert not err.has_class("hidden")
            child.query_one("#model-input", Input).value = "claude-3"
            child.action_save()
            await pilot.pause()
            assert err.has_class("hidden")
            assert len(saved) == 1
            assert saved[0].model == "claude-3"
