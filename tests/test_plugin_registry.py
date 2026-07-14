"""Tests for PluginRegistry, PluginState, PluginManifest."""

from __future__ import annotations

import time

import pytest

from cscode.core.plugin.registry import PluginManifest, PluginRegistry, PluginState


class TestPluginState:
    def test_enum_values(self) -> None:
        assert PluginState.UNKNOWN.value == "unknown"
        assert PluginState.DISCOVERED.value == "discovered"
        assert PluginState.LOADED.value == "loaded"
        assert PluginState.ACTIVE.value == "active"
        assert PluginState.INACTIVE.value == "inactive"

    def test_enum_members(self) -> None:
        assert set(PluginState) == {
            PluginState.UNKNOWN,
            PluginState.DISCOVERED,
            PluginState.LOADED,
            PluginState.ACTIVE,
            PluginState.INACTIVE,
        }


class TestPluginManifest:
    def test_minimal_manifest(self) -> None:
        m = PluginManifest(id="my-plugin", name="My Plugin", version="1.0.0")
        assert m.id == "my-plugin"
        assert m.name == "My Plugin"
        assert m.version == "1.0.0"
        assert m.state == PluginState.DISCOVERED
        assert m.installed_at == 0.0
        assert m.activated_at is None

    def test_full_manifest(self) -> None:
        now = time.time()
        m = PluginManifest(
            id="test-plugin",
            name="Test Plugin",
            version="2.0.0",
            description="A test plugin",
            author="test@example.com",
            source="/tmp/plugins/test",
            state=PluginState.ACTIVE,
            hooks=["session.start", "tool.call"],
            tools=["read", "write"],
            commands=["deploy"],
            installed_at=now,
            activated_at=now,
        )
        assert m.author == "test@example.com"
        assert m.hooks == ["session.start", "tool.call"]
        assert m.tools == ["read", "write"]
        assert m.commands == ["deploy"]


class TestPluginRegistry:
    def test_register_and_get(self) -> None:
        reg = PluginRegistry()
        m = PluginManifest(id="p1", name="Plugin 1", version="0.1.0")
        reg.register(m)
        assert reg.get("p1") is m

    def test_register_duplicate_raises(self) -> None:
        reg = PluginRegistry()
        reg.register(PluginManifest(id="p1", name="P1", version="1.0"))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(PluginManifest(id="p1", name="P1 dup", version="1.0"))

    def test_unregister(self) -> None:
        reg = PluginRegistry()
        reg.register(PluginManifest(id="p1", name="P1", version="1.0"))
        reg.unregister("p1")
        assert reg.get("p1") is None

    def test_unregister_missing_raises(self) -> None:
        reg = PluginRegistry()
        with pytest.raises(KeyError):
            reg.unregister("nonexistent")

    def test_list_empty(self) -> None:
        reg = PluginRegistry()
        assert reg.list() == []

    def test_list_multiple(self) -> None:
        reg = PluginRegistry()
        reg.register(PluginManifest(id="a", name="A", version="1.0"))
        reg.register(PluginManifest(id="b", name="B", version="1.0"))
        assert len(reg.list()) == 2

    def test_update_state(self) -> None:
        reg = PluginRegistry()
        m = PluginManifest(id="p1", name="P1", version="1.0")
        reg.register(m)
        reg.update_state("p1", PluginState.ACTIVE)
        assert m.state == PluginState.ACTIVE
        assert m.activated_at is not None

    def test_update_state_inactive(self) -> None:
        reg = PluginRegistry()
        m = PluginManifest(id="p1", name="P1", version="1.0")
        reg.register(m)
        reg.update_state("p1", PluginState.INACTIVE)
        assert m.state == PluginState.INACTIVE
        assert m.activated_at is None

    def test_update_state_missing_raises(self) -> None:
        reg = PluginRegistry()
        with pytest.raises(KeyError):
            reg.update_state("nonexistent", PluginState.ACTIVE)

    def test_count_total(self) -> None:
        reg = PluginRegistry()
        assert reg.count() == 0
        reg.register(PluginManifest(id="a", name="A", version="1.0"))
        reg.register(PluginManifest(id="b", name="B", version="1.0"))
        assert reg.count() == 2

    def test_count_by_state(self) -> None:
        reg = PluginRegistry()
        m1 = PluginManifest(id="a", name="A", version="1.0", state=PluginState.DISCOVERED)
        m2 = PluginManifest(id="b", name="B", version="1.0", state=PluginState.ACTIVE)
        m3 = PluginManifest(id="c", name="C", version="1.0", state=PluginState.DISCOVERED)
        reg.register(m1)
        reg.register(m2)
        reg.register(m3)
        assert reg.count(PluginState.DISCOVERED) == 2
        assert reg.count(PluginState.ACTIVE) == 1
