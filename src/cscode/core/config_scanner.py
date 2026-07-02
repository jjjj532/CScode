from __future__ import annotations

from pathlib import Path
from typing import Any

from cscode.core.config import Config
from cscode.core.config_variable import resolve_config as resolve_vars
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "scan_config",
    "ConfigSource",
    "load_config_from_layers",
    "write_project_config",
    "find_project_root",
]

_CONFIG_FILES = ("config.yaml", "config.yml", "config.json")


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk up from *start* (default CWD) looking for a project marker.

    Markers checked (in order):
    - ``.git/``
    - ``.opencode/``
    - ``.cscode/``
    - ``pyproject.toml``
    - ``package.json``

    Returns the first ancestor directory containing any marker, or ``None``.
    """
    current = (start or Path.cwd()).resolve()
    for parent in [current] + list(current.parents):
        markers = [
            parent / ".git",
            parent / ".opencode",
            parent / ".cscode",
            parent / "pyproject.toml",
            parent / "package.json",
        ]
        if any(m.exists() for m in markers):
            return parent
    return None


class ConfigSource:
    """Discovered config file with metadata."""

    def __init__(self, path: Path, layer: str) -> None:
        self.path = path
        self.layer = layer  # "global", "project", or "local"

    def load(self) -> dict[str, Any]:
        raw = self.path.read_text()
        if self.path.suffix == ".json":
            import json
            return dict(json.loads(raw))
        import yaml
        return dict(yaml.safe_load(raw) or {})

    def __repr__(self) -> str:
        return f"ConfigSource({self.path}, layer={self.layer})"


def scan_config(
    search_dirs: list[Path] | None = None,
    local_dirs: list[Path] | None = None,
) -> list[ConfigSource]:
    """Discover config files across global/project/local layers.

    Parameters
    ----------
    search_dirs:
        Directories to search for ``.cscode/config.yaml`` (project layer)
        and ``config.yaml`` directly (global layer).  Defaults to
        ``[~/.config/cscode/, <project-root>/.cscode/]`` when *local_dirs*
        is also omitted.
    local_dirs:
        Directories to search for ``config.json`` or ``config.yaml``
        (local layer, highest priority).  Defaults to
        ``[<project-root>/.opencode/]``.

    Returns a list of :class:`ConfigSource` ordered by increasing priority
    (global → project → local).
    """
    if search_dirs is None and local_dirs is None:
        home = Path.home() / ".config" / "cscode"
        project_root = find_project_root()
        search_dirs = [home]
        if project_root:
            search_dirs.append(project_root / ".cscode")
        local_dirs = [project_root / ".opencode"] if project_root else []

    sources: list[ConfigSource] = []

    # Global & project layers (search_dirs)
    if search_dirs:
        for base in search_dirs:
            for name in _CONFIG_FILES:
                p = base / name
                if p.exists():
                    layer = "project" if ".cscode" in str(base) else "global"
                    sources.append(ConfigSource(p, layer))

    # Local layer (local_dirs)
    if local_dirs:
        for base in local_dirs:
            for name in _CONFIG_FILES:
                p = base / name
                if p.exists():
                    sources.append(ConfigSource(p, "local"))

    return sources


def load_config_from_layers(
    search_dirs: list[Path] | None = None,
    local_dirs: list[Path] | None = None,
    cli_overrides: dict[str, Any] | None = None,
    db_config: dict[str, Any] | None = None,
) -> Config:
    """Load config using the 3-layer scanner + variable resolution.

    Priority (lowest → highest):
      1. Config defaults
      2. Global config (``~/.config/cscode/config.yaml``)
      3. Project config (``<project>/.cscode/config.yaml``)
      4. Local config (``<project>/.opencode/config.json``)
      5. Environment variables
      6. Database (user-saved config)
      7. CLI overrides

    Variable substitution (``${env.VAR}``) is applied to all values from
    file-based sources (layers 2-4).
    """
    sources = scan_config(search_dirs=search_dirs, local_dirs=local_dirs)

    # Start from defaults, then layer in sources
    cfg = Config()
    for src in sources:
        data = src.load()
        resolved = resolve_vars(data)
        cfg = cfg.merge(Config.from_dict(resolved))

    # Environment variables (above file layers, below DB/CLI)
    env_cfg = Config.from_env()
    if env_cfg is not None:
        cfg = cfg.merge(env_cfg)

    # Database and CLI overrides
    if db_config:
        cfg = cfg.merge(Config.from_dict(db_config))
    if cli_overrides:
        cfg = cfg.merge(Config.from_dict(cli_overrides))

    logger.info(
        "Config loaded: provider=%s model=%s api_base=%s",
        cfg.provider,
        cfg.model,
        cfg.api_base or "default",
    )
    return cfg


def write_project_config(data: dict[str, Any], root: Path | None = None) -> Path:
    """Write config to the project-local ``.opencode/config.json``.

    Creates the ``.opencode/`` directory if it does not exist.
    """
    project_root = root or find_project_root() or Path.cwd()
    config_dir = project_root / ".opencode"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.json"

    import json
    config_path.write_text(json.dumps(data, indent=2, default=str) + "\n")
    logger.info("Project config written to %s", config_path)
    return config_path
