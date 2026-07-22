from __future__ import annotations

from typing import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label

from cscode.core.config import Config


class SettingsScreen(Screen[None]):
    """Screen that edits Config fields with validation and save/cancel.

    Key bindings:
        - ``escape`` — cancel and return
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    def __init__(
        self,
        config: Config,
        save_callback: Callable[[Config], None] | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._save_callback = save_callback

    def compose(self) -> ComposeResult:
        yield Header()
        yield ScrollableContainer(
            Label("Settings", id="settings-title", classes="screen-title"),
            Label("Provider", classes="field-label"),
            Input(value=self._config.provider, id="provider-input", classes="settings-input"),
            Label("Model", classes="field-label"),
            Input(value=self._config.model, id="model-input", classes="settings-input"),
            Label("Temperature (0.0 - 2.0)", classes="field-label"),
            Input(value=str(self._config.temperature), id="temperature-input", classes="settings-input"),
            Label("Theme", classes="field-label"),
            Input(value=self._config.theme, id="theme-input", classes="settings-input"),
            Label("System Prompt", classes="field-label"),
            Input(value=self._config.system_prompt or "", id="prompt-input", classes="settings-input"),
            Label("", id="validation-error", classes="error hidden"),
            Horizontal(
                Button("Save", id="save-btn", variant="primary"),
                Button("Cancel", id="cancel-btn", variant="default"),
                classes="button-row",
            ),
            id="settings-scroll",
        )
        yield Footer()

    def action_cancel(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self.action_save()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_save(self) -> None:
        error_label = self.query_one("#validation-error", Label)

        provider = self.query_one("#provider-input", Input).value.strip()
        model = self.query_one("#model-input", Input).value.strip()
        temperature_str = self.query_one("#temperature-input", Input).value.strip()
        theme = self.query_one("#theme-input", Input).value.strip()
        system_prompt = self.query_one("#prompt-input", Input).value.strip()

        if not model:
            error_label.update("Model cannot be empty")
            error_label.remove_class("hidden")
            self.query_one("#model-input", Input).focus()
            return

        try:
            temperature = float(temperature_str) if temperature_str else 0.3
        except ValueError:
            error_label.update(f"Invalid temperature: {temperature_str}")
            error_label.remove_class("hidden")
            self.query_one("#temperature-input", Input).focus()
            return

        if not 0.0 <= temperature <= 2.0:
            error_label.update(f"Temperature must be between 0.0 and 2.0, got {temperature}")
            error_label.remove_class("hidden")
            self.query_one("#temperature-input", Input).focus()
            return

        error_label.add_class("hidden")

        updated = Config(
            provider=provider or "openai",
            model=model,
            temperature=temperature,
            theme=theme or "catppuccin",
            system_prompt=system_prompt or self._config.system_prompt,
            api_key=self._config.api_key,
            api_base=self._config.api_base,
            max_tokens=self._config.max_tokens,
            top_p=self._config.top_p,
            tui_cwd=self._config.tui_cwd,
            tui_host_attention=self._config.tui_host_attention,
        )

        if self._save_callback is not None:
            self._save_callback(updated)

        self.app.pop_screen()
