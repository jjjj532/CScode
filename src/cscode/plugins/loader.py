from __future__ import annotations

import importlib
import sys
from pathlib import Path

from cscode.tools.base import BaseTool
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class PluginLoader:
    async def load_plugin(self, plugin_path: str) -> list[BaseTool]:
        logger.debug("PluginLoader.load_plugin: path=%s", plugin_path)
        path = Path(plugin_path).resolve()
        if not path.exists() or not path.is_dir():
            logger.debug("PluginLoader.load_plugin: path not found or not a dir: %s", path)
            return []
        if not (path / "__init__.py").exists():
            logger.debug("PluginLoader.load_plugin: no __init__.py in %s", path)
            return []

        plugin_name = path.name
        if str(path.parent) not in sys.path:
            sys.path.insert(0, str(path.parent))

        try:
            module = importlib.import_module(plugin_name)
            importlib.reload(module)
            tools = getattr(module, "__tools__", [])
            logger.info("PluginLoader.load_plugin: loaded plugin=%s tools=%d", plugin_name, len(tools))
            return list(tools)
        except Exception:
            logger.exception("PluginLoader.load_plugin: failed plugin=%s", plugin_name)
            return []

    async def discover(self, plugin_dirs: list[str]) -> list[BaseTool]:
        logger.info("PluginLoader.discover: dirs=%s", plugin_dirs)
        all_tools: list[BaseTool] = []
        seen_names: set[str] = set()

        for plugin_dir in plugin_dirs:
            path = Path(plugin_dir)
            if not path.exists():
                logger.debug("PluginLoader.discover: dir not found: %s", plugin_dir)
                continue
            for item in path.iterdir():
                if item.is_dir() and (item / "__init__.py").exists():
                    tools = await self.load_plugin(str(item))
                    for tool in tools:
                        if tool.name not in seen_names:
                            all_tools.append(tool)
                            seen_names.add(tool.name)
        logger.info("PluginLoader.discover: done total_tools=%d", len(all_tools))
        return all_tools
