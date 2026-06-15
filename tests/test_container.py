from __future__ import annotations

from typing import Protocol

import pytest

from cscode.core.container import ServiceContainer, ServiceProvider
from cscode.core.events import EventBus
from cscode.core.permissions import PermissionService


class _Greeter(Protocol):
    def greet(self, name: str) -> str: ...


class HelloGreeter:
    def greet(self, name: str) -> str:
        return f"Hello, {name}!"


class GoodbyeGreeter:
    def greet(self, name: str) -> str:
        return f"Goodbye, {name}!"


class TestServiceContainer:
    def test_register_and_get(self) -> None:
        container = ServiceContainer()
        container.register("greeter", HelloGreeter())
        greeter = container.get("greeter")
        assert isinstance(greeter, HelloGreeter)
        assert greeter.greet("World") == "Hello, World!"

    def test_get_unregistered_raises(self) -> None:
        container = ServiceContainer()
        with pytest.raises(KeyError, match="Service 'nonexistent' not registered"):
            container.get("nonexistent")

    def test_has_service(self) -> None:
        container = ServiceContainer()
        assert not container.has("greeter")
        container.register("greeter", HelloGreeter())
        assert container.has("greeter")

    def test_register_overwrites(self) -> None:
        container = ServiceContainer()
        container.register("greeter", HelloGreeter())
        container.register("greeter", GoodbyeGreeter())
        greeter = container.get("greeter")
        assert isinstance(greeter, GoodbyeGreeter)
        assert greeter.greet("World") == "Goodbye, World!"

    def test_get_or_none(self) -> None:
        container = ServiceContainer()
        assert container.get_or_none("greeter") is None
        container.register("greeter", HelloGreeter())
        assert container.get_or_none("greeter") is not None

    def test_get_or_default(self) -> None:
        container = ServiceContainer()
        default = HelloGreeter()
        assert container.get_or_default("greeter", default) is default
        custom = GoodbyeGreeter()
        container.register("greeter", custom)
        assert container.get_or_default("greeter", default) is custom

    def test_remove_service(self) -> None:
        container = ServiceContainer()
        container.register("greeter", HelloGreeter())
        container.remove("greeter")
        assert not container.has("greeter")

    def test_clear_all(self) -> None:
        container = ServiceContainer()
        container.register("a", 1)
        container.register("b", 2)
        container.clear()
        assert not container.has("a")
        assert not container.has("b")

    def test_lazy_factory(self) -> None:
        container = ServiceContainer()
        container.register_factory("counter", lambda: _Counter())

        c1 = container.get("counter")
        c2 = container.get("counter")
        assert c1 is c2  # singleton


class _Counter:
    def __init__(self) -> None:
        self.count = 0

    def increment(self) -> int:
        self.count += 1
        return self.count


class TestServiceProvider:
    def test_provider_registers_default_services(self) -> None:
        provider = ServiceProvider()
        container = provider.create_container()
        assert container.has("event_bus")
        assert container.has("permission_service")

    def test_provider_creates_singleton_event_bus(self) -> None:
        provider = ServiceProvider()
        c1 = provider.create_container()
        c2 = provider.create_container()
        assert c1.get("event_bus") is c2.get("event_bus")

    def test_permission_service_wired_to_event_bus(self) -> None:
        provider = ServiceProvider()
        container = provider.create_container()
        bus = container.get("event_bus")
        perms = container.get("permission_service")
        assert perms._bus is bus  # wired correctly
