"""Plugin system v2 — lifecycle, registry, hooks, and discovery."""

from cscode.core.plugin.api import CommandDef, PluginAPI, ProviderDef, SkillDef, UIExtension
from cscode.core.plugin.discovery import PluginDiscoverer
from cscode.core.plugin.hooks import HookPoint, HookRegistry
from cscode.core.plugin.host import PluginHost
from cscode.core.plugin.registry import PluginManifest, PluginRegistry, PluginState

__all__ = [
    "CommandDef",
    "HookPoint",
    "HookRegistry",
    "PluginAPI",
    "PluginDiscoverer",
    "PluginHost",
    "PluginManifest",
    "PluginRegistry",
    "PluginState",
    "ProviderDef",
    "SkillDef",
    "UIExtension",
]
