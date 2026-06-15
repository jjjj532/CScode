from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PluginManifest:
    name: str
    version: str
    description: str = ""
    author: str = ""
    hooks: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)


def load_manifest(path: str) -> PluginManifest | None:
    try:
        p = Path(path)
        if not p.exists():
            return None
        data = json.loads(p.read_text())
        return PluginManifest(
            name=data.get("name", "unknown"),
            version=data.get("version", "0.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            hooks=data.get("hooks", []),
            tools=data.get("tools", []),
        )
    except (json.JSONDecodeError, FileNotFoundError, KeyError):
        return None
