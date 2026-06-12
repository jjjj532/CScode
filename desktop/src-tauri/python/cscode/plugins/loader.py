from __future__ import annotations

import importlib
import sys
from pathlib import Path

from cscode.tools.base import BaseTool


class PluginLoader:
    async def load_plugin(self, plugin_path: str) -> list[BaseTool]:
        path = Path(plugin_path).resolve()
        if not path.exists() or not path.is_dir():
            return []
        if not (path / "__init__.py").exists():
            return []

        plugin_name = path.name
        if str(path.parent) not in sys.path:
            sys.path.insert(0, str(path.parent))

        try:
            module = importlib.import_module(plugin_name)
            importlib.reload(module)
            tools = getattr(module, "__tools__", [])
            return list(tools)
        except Exception:
            return []

    async def discover(self, plugin_dirs: list[str]) -> list[BaseTool]:
        all_tools: list[BaseTool] = []
        seen_names: set[str] = set()

        for plugin_dir in plugin_dirs:
            path = Path(plugin_dir)
            if not path.exists():
                continue
            for item in path.iterdir():
                if item.is_dir() and (item / "__init__.py").exists():
                    tools = await self.load_plugin(str(item))
                    for tool in tools:
                        if tool.name not in seen_names:
                            all_tools.append(tool)
                            seen_names.add(tool.name)
        return all_tools
