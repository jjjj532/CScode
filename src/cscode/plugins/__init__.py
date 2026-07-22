from __future__ import annotations

from cscode.plugins.bridge import build_activate_func, detect_sdk_instances
from cscode.plugins.hooks import PluginHookManager
from cscode.plugins.loader import PluginLoader
from cscode.plugins.manifest import PluginManifest, load_manifest
from cscode.plugins.sdk import PluginSDK

__all__ = [
    "PluginLoader",
    "PluginManifest",
    "load_manifest",
    "PluginHookManager",
    "PluginSDK",
    "build_activate_func",
    "detect_sdk_instances",
]
