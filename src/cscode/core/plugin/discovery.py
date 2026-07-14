"""Plugin discovery — find plugins from local paths, pip packages, or git repos."""

from __future__ import annotations

import sys
from pathlib import Path

from cscode.core.plugin.registry import PluginManifest, PluginState
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


def _discover_from_directory(path: Path) -> list[PluginManifest]:
    """Scan a directory for plugin packages."""
    results: list[PluginManifest] = []
    if not path.exists() or not path.is_dir():
        return results

    for item in path.iterdir():
        if not item.is_dir():
            continue
        init_file = item / "__init__.py"
        if not init_file.exists():
            continue

        manifest = _try_load_manifest(item)
        if manifest is not None:
            results.append(manifest)

    return results


def _try_load_manifest(plugin_dir: Path) -> PluginManifest | None:
    """Attempt to load a plugin manifest from a plugin directory."""
    from cscode.plugins.manifest import load_manifest  # lazy: avoid circular

    plugin_id = plugin_dir.name

    # Try JSON manifest file first
    manifest_file = plugin_dir / "plugin.json"
    if manifest_file.exists():
        m = load_manifest(str(manifest_file))
        if m is not None:
            return PluginManifest(
                id=plugin_id,
                name=m.name,
                version=m.version,
                description=m.description,
                author=m.author,
                source=str(plugin_dir),
                state=PluginState.DISCOVERED,
                hooks=m.hooks,
                tools=m.tools,
            )

    # Fallback: try __init__.py for PluginSDK instance
    init_file = plugin_dir / "__init__.py"
    if init_file.exists():
        name = _try_extract_name(init_file)
        return PluginManifest(
            id=plugin_id,
            name=name or plugin_id,
            version="0.0.0",
            source=str(plugin_dir),
            state=PluginState.DISCOVERED,
        )

    return None


def _try_extract_name(init_file: Path) -> str | None:
    """Minimal extraction of plugin name from __init__.py without full import."""
    try:
        text = init_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("__plugin_name__"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    return parts[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


class PluginDiscoverer:
    """Discovers plugins from multiple source types.

    Supports:
      - Local directory scanning
      - Pip-installed packages
      - Git repository URLs
    """

    def __init__(self) -> None:
        self._pip_packages: dict[str, PluginManifest] = {}

    async def discover_local(self, paths: list[str]) -> list[PluginManifest]:
        """Scan local directories for plugin packages."""
        results: list[PluginManifest] = []
        seen_ids: set[str] = set()

        for path_str in paths:
            manifests = _discover_from_directory(Path(path_str).resolve())
            for m in manifests:
                if m.id not in seen_ids:
                    results.append(m)
                    seen_ids.add(m.id)

        logger.info("PluginDiscoverer.discover_local: found %d plugins", len(results))
        return results

    async def discover_pip(self, packages: list[str]) -> list[PluginManifest]:
        """Discover plugins from pip-installed packages.

        Each package is imported to check for a cscode_plugin attribute
        or a plugin manifest.
        """
        results: list[PluginManifest] = []
        for pkg_name in packages:
            if pkg_name in self._pip_packages:
                results.append(self._pip_packages[pkg_name])
                continue
            manifest = self._try_discover_pip_package(pkg_name)
            if manifest is not None:
                self._pip_packages[pkg_name] = manifest
                results.append(manifest)
        return results

    async def discover_git(self, urls: list[str]) -> list[PluginManifest]:
        """Discover plugins from git repository URLs.

        Clones to a temp dir and scans for plugin manifests.
        NOTE: For Phase 0, this is a stub that parses the URL only.
        """
        results: list[PluginManifest] = []
        for url in urls:
            repo_name = url.rstrip("/").split("/")[-1].removesuffix(".git")
            manifest = PluginManifest(
                id=f"git:{repo_name}",
                name=repo_name,
                version="0.0.0",
                source=url,
                state=PluginState.DISCOVERED,
            )
            results.append(manifest)
        return results

    def _try_discover_pip_package(self, pkg_name: str) -> PluginManifest | None:
        """Try to discover a pip-installed plugin package."""
        try:
            __import__(pkg_name)
            mod = sys.modules.get(pkg_name)
            if mod is None:
                return None
            manifest = getattr(mod, "cscode_manifest", None)
            if manifest is not None:
                return PluginManifest(
                    id=pkg_name,
                    name=manifest.get("name", pkg_name),
                    version=manifest.get("version", "0.0.0"),
                    description=manifest.get("description", ""),
                    author=manifest.get("author", ""),
                    source=f"pip:{pkg_name}",
                    state=PluginState.DISCOVERED,
                    hooks=manifest.get("hooks", []),
                    tools=manifest.get("tools", []),
                )
            # No manifest attr — register as generic plugin
            return PluginManifest(
                id=pkg_name,
                name=pkg_name,
                version="0.0.0",
                source=f"pip:{pkg_name}",
                state=PluginState.DISCOVERED,
            )
        except Exception:
            logger.debug("PluginDiscoverer: failed to inspect pip package %s", pkg_name)
            return None
