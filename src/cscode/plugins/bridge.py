"""Bridge between PluginSDK and PluginHost lifecycle.

Detects PluginSDK instances in plugin modules and generates
``activate(api)`` / ``deactivate()`` callbacks that PluginHost
can use, so SDK-style plugins get full lifecycle management.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

from cscode.core.plugin.api import PluginAPI
from cscode.plugins.sdk import PluginSDK


def detect_sdk_instances(module: ModuleType) -> list[PluginSDK]:
    """Scan a module for ``PluginSDK`` instances.

    Iterates over the module's attributes and collects all that
    are instances of ``PluginSDK``.

    Args:
        module: The imported plugin module to scan.

    Returns:
        List of ``PluginSDK`` instances found in the module.
    """
    instances: list[PluginSDK] = []
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, PluginSDK):
            instances.append(attr)
    return instances


def build_activate_func(
    sdk_instances: list[PluginSDK],
) -> Callable[[PluginAPI], None]:
    """Build an ``activate(api)`` callback from ``PluginSDK`` instances.

    The generated function registers all tools from each SDK instance
    via the ``PluginAPI.register_tool()`` method.

    Args:
        sdk_instances: List of ``PluginSDK`` instances whose tools
            should be registered during activation.

    Returns:
        A callable compatible with the ``activate(api)`` convention
        that PluginHost expects.
    """

    def activate(api: PluginAPI) -> None:
        for sdk in sdk_instances:
            for tool_cls in sdk.tools.values():
                api.register_tool(tool_cls)

    return activate
