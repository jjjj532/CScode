from __future__ import annotations

from typing import Any, Callable

from cscode.core.events import EventBus
from cscode.core.permissions import PermissionService


class ServiceContainer:
    def __init__(self) -> None:
        self._instances: dict[str, Any] = {}
        self._factories: dict[str, Callable[[], Any]] = {}

    def register(self, name: str, instance: Any) -> None:
        self._instances[name] = instance

    def register_factory(self, name: str, factory: Callable[[], Any]) -> None:
        self._factories[name] = factory

    def get(self, name: str) -> Any:
        if name in self._instances:
            return self._instances[name]
        if name in self._factories:
            instance = self._factories[name]()
            self._instances[name] = instance
            return instance
        raise KeyError(f"Service '{name}' not registered")

    def get_or_none(self, name: str) -> Any | None:
        try:
            return self.get(name)
        except KeyError:
            return None

    def get_or_default(self, name: str, default: Any) -> Any:
        try:
            return self.get(name)
        except KeyError:
            return default

    def has(self, name: str) -> bool:
        return name in self._instances or name in self._factories

    def remove(self, name: str) -> None:
        self._instances.pop(name, None)
        self._factories.pop(name, None)

    def clear(self) -> None:
        self._instances.clear()
        self._factories.clear()


class ServiceProvider:
    _event_bus: EventBus | None = None

    @classmethod
    def create_container(cls) -> ServiceContainer:
        container = ServiceContainer()

        if cls._event_bus is None:
            cls._event_bus = EventBus()
        container.register("event_bus", cls._event_bus)

        permission_service = PermissionService(cls._event_bus)
        container.register("permission_service", permission_service)

        return container
