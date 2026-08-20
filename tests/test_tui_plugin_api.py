"""G-6 TUI 插件化 — 契约测试（spec §5.2.3 接口 + §5.2.4 验收标准 1-3）。

验收标准 4（既有 test_tui_*.py 全通过）由全量回归在 VERIFY 阶段验证。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from cscode.tui.commands import CommandDef, CommandRegistry
from cscode.tui.plugin_api import TuiPluginAPI, TuiPluginLoader


# ─── Fixtures ─────────────────────────────────────────────────────


class _FakeHost:
    """Duck-typed host the TuiPluginAPI talks to (no real Textual app)."""

    def __init__(self) -> None:
        self.registry = CommandRegistry()
        self.pushed_screens: list[tuple[str, dict | None]] = []
        self.installed_themes: dict[str, object] = {}
        self.set_theme_calls: list[str] = []
        self.kv_store: dict[str, object] = {}
        self._themes = {"catppuccin": object(), "nord": object()}

    def navigate(self, screen: str, params: dict | None = None) -> None:
        self.pushed_screens.append((screen, params))

    def install_theme(self, name: str, theme: object) -> None:
        self.installed_themes[name] = theme

    def set_theme(self, name: str) -> bool:
        if name not in self._themes and name not in self.installed_themes:
            return False
        self.set_theme_calls.append(name)
        return True

    def get_kv(self) -> dict[str, object]:
        return self.kv_store


@pytest.fixture
def host() -> _FakeHost:
    return _FakeHost()


@pytest.fixture
def api(host: _FakeHost) -> TuiPluginAPI:
    return TuiPluginAPI(host, plugin_id="test-plugin")


# ─── CommandRegistry ──────────────────────────────────────────────


def test_register_command_normalizes_slash(host: _FakeHost) -> None:
    handler = lambda _args: None  # noqa: E731
    host.registry.register("hello", handler, category="general")
    names = [c.name for c in host.registry.list()]
    assert "/hello" in names


async def test_dispatch_invokes_handler_with_args(host: _FakeHost) -> None:
    captured: list[str] = []

    async def handler(args: str) -> None:
        captured.append(args)

    host.registry.register("ping", handler, category="general")
    result = host.registry.dispatch("/ping", "hello world")
    await asyncio.sleep(0)
    assert result is True
    assert captured == ["hello world"]


def test_dispatch_unknown_returns_false(host: _FakeHost) -> None:
    assert host.registry.dispatch("/nonexistent", "") is False


async def test_aliases_dispatch_to_same_handler(host: _FakeHost) -> None:
    captured: list[str] = []

    async def handler(args: str) -> None:
        captured.append(args)

    host.registry.register("hello", handler, category="general", aliases=["/hi", "/hey"])
    assert host.registry.dispatch("/hi", "a") is True
    assert host.registry.dispatch("/hey", "b") is True
    assert host.registry.dispatch("/hello", "c") is True
    await asyncio.sleep(0)
    assert captured == ["a", "b", "c"]


def test_commands_grouped_by_category(host: _FakeHost) -> None:
    host.registry.register("one", lambda _: None, category="session")  # noqa: E731
    host.registry.register("two", lambda _: None, category="model")  # noqa: E731
    host.registry.register("three", lambda _: None, category="session")  # noqa: E731

    session_names = [c.name for c in host.registry.by_category("session")]
    model_names = [c.name for c in host.registry.by_category("model")]
    assert session_names == ["/one", "/three"]
    assert model_names == ["/two"]


def test_command_completion_list_derived_from_registry(host: _FakeHost) -> None:
    host.registry.register("hello", lambda _: None, category="general")  # noqa: E731
    host.registry.register("help", lambda _: None, category="general")  # noqa: E731
    completions = host.registry.completion_commands()
    assert "/hello" in completions
    assert "/help" in completions


# ─── TuiPluginAPI ─────────────────────────────────────────────────


def test_plugin_api_register_command_delegates_to_registry(api: TuiPluginAPI, host: _FakeHost) -> None:
    api.register_command("plugin-cmd", lambda _: None, category="agent")  # noqa: E731
    names = [c.name for c in host.registry.list()]
    assert "/plugin-cmd" in names
    cmd = next(c for c in host.registry.list() if c.name == "/plugin-cmd")
    assert cmd.category == "agent"
    assert cmd.plugin_id == "test-plugin"


def test_plugin_api_navigate_pushes_screen(api: TuiPluginAPI, host: _FakeHost) -> None:
    api.navigate("settings", {"tab": "model"})
    assert host.pushed_screens == [("settings", {"tab": "model"})]


def test_plugin_api_navigate_no_params(api: TuiPluginAPI, host: _FakeHost) -> None:
    api.navigate("sessions")
    assert host.pushed_screens == [("sessions", None)]


def test_plugin_api_theme_set_delegates_to_host(api: TuiPluginAPI, host: _FakeHost) -> None:
    assert api.theme_set("nord") is True
    assert host.set_theme_calls == ["nord"]
    assert api.theme_set("unknown-theme") is False


def test_plugin_api_theme_install(api: TuiPluginAPI, host: _FakeHost) -> None:
    theme = object()
    api.theme_install("solarized", theme)
    assert host.installed_themes["solarized"] is theme


def test_plugin_api_kv_state_roundtrip(api: TuiPluginAPI) -> None:
    api.kv_set("counter", 3)
    assert api.kv_get("counter") == 3
    assert api.kv_get("missing") is None


# ─── Loader / 生命周期（验收标准 3） ────────────────────────────────


def _write_plugin(tmp_path: Path, plugin_id: str, body: str) -> Path:
    plugin_dir = tmp_path / plugin_id
    plugin_dir.mkdir()
    (plugin_dir / "plugin.py").write_text(body)
    return plugin_dir


PLUGIN_WITH_COMMAND = """
from cscode.tui.plugin_api import TuiPluginAPI

def install(api: TuiPluginAPI) -> None:
    async def handler(args: str) -> None:
        api.kv_set("last_args", args)
    api.register_command("hello", handler, category="general", aliases=["/hey"])
"""


def test_loader_installs_plugin_module(tmp_path: Path, host: _FakeHost) -> None:
    plugin_dir = _write_plugin(tmp_path, "greeter", PLUGIN_WITH_COMMAND)
    loader = TuiPluginLoader(host)
    apis = loader.load([str(plugin_dir)])

    assert len(apis) == 1
    names = [c.name for c in host.registry.list()]
    assert "/hello" in names
    completions = host.registry.completion_commands()
    assert "/hey" in completions


def test_loader_deactivate_removes_all_plugin_commands(tmp_path: Path, host: _FakeHost) -> None:
    plugin_dir = _write_plugin(tmp_path, "greeter", PLUGIN_WITH_COMMAND)
    loader = TuiPluginLoader(host)
    loader.load([str(plugin_dir)])
    assert len(host.registry.list()) == 1

    loader.deactivate_all()
    assert host.registry.list() == []


def test_loader_handles_plugin_without_install(tmp_path: Path, host: _FakeHost) -> None:
    plugin_dir = _write_plugin(tmp_path, "empty", "# no install() function\n")
    loader = TuiPluginLoader(host)
    apis = loader.load([str(plugin_dir)])
    assert apis == []
    assert host.registry.list() == []


async def test_plugin_command_dispatchable_through_app_handler(tmp_path: Path) -> None:
    """验收标准 1：插件命令在命令面板（注册表）出现并可触发。"""
    from unittest.mock import MagicMock

    from cscode.tui.app import CScodeTUI

    plugin_dir = _write_plugin(tmp_path, "greeter", PLUGIN_WITH_COMMAND)

    app = CScodeTUI()
    apis = app.load_plugin_dir(str(plugin_dir))
    assert len(apis) == 1

    output = MagicMock()
    handled = app._handle_session_command("/hello", output)  # type: ignore[attr-defined]
    await asyncio.sleep(0)
    assert handled is True
    assert apis[0].kv_get("last_args") == ""


def test_plugin_commands_coexist_with_builtin(tmp_path: Path) -> None:
    """验收标准 2：插件命令与既有 TUI 命令共存。"""
    from unittest.mock import MagicMock

    from cscode.tui.app import CScodeTUI

    plugin_dir = _write_plugin(tmp_path, "greeter", PLUGIN_WITH_COMMAND)
    app = CScodeTUI()
    app.load_plugin_dir(str(plugin_dir))

    output = MagicMock()
    # 既有内置命令仍然工作
    assert app._handle_session_command("/new", output) is True  # type: ignore[attr-defined]
    # 插件命令也工作
    assert app._handle_session_command("/hello", output) is True  # type: ignore[attr-defined]
