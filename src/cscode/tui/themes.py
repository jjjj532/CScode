from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Theme:
    name: str
    primary: str
    surface: str
    text: str
    muted: str
    error: str
    warning: str
    success: str

    def to_css_variables(self) -> str:
        return f"""$primary: {self.primary};
$surface: {self.surface};
$text: {self.text};
$text-muted: {self.muted};
$error: {self.error};
$warning: {self.warning};
$success: {self.success};
$background: {self.surface};"""


PRESET_THEMES: dict[str, Theme] = {
    "catppuccin": Theme(
        name="catppuccin",
        primary="#89b4fa",
        surface="#1e1e2e",
        text="#cdd6f4",
        muted="#6c7086",
        error="#f38ba8",
        warning="#fab387",
        success="#a6e3a1",
    ),
    "dracula": Theme(
        name="dracula",
        primary="#bd93f9",
        surface="#282a36",
        text="#f8f8f2",
        muted="#6272a4",
        error="#ff5555",
        warning="#f1fa8c",
        success="#50fa7b",
    ),
    "monokai": Theme(
        name="monokai",
        primary="#66d9ef",
        surface="#272822",
        text="#f8f8f2",
        muted="#75715e",
        error="#f92672",
        warning="#e6db74",
        success="#a6e22e",
    ),
    "nord": Theme(
        name="nord",
        primary="#88c0d0",
        surface="#2e3440",
        text="#eceff4",
        muted="#616e87",
        error="#bf616a",
        warning="#ebcb8b",
        success="#a3be8c",
    ),
    "github-dark": Theme(
        name="github-dark",
        primary="#58a6ff",
        surface="#0d1117",
        text="#c9d1d9",
        muted="#8b949e",
        error="#f85149",
        warning="#d29922",
        success="#3fb950",
    ),
    "light": Theme(
        name="light",
        primary="#0969da",
        surface="#ffffff",
        text="#1f2328",
        muted="#656d76",
        error="#cf222e",
        warning="#bf8700",
        success="#1a7f37",
    ),
}


def apply_theme(theme_name: str) -> str | None:
    """Get CSS variables string for a named theme, or None if not found."""
    theme = PRESET_THEMES.get(theme_name)
    if theme is None:
        return None
    return theme.to_css_variables()
