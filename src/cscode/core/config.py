from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from cscode.storage.db import Database


from cscode.core.errors import ConfigError
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Config:
    provider: str = "openai"
    model: str = "gpt-4o"
    api_base: str | None = None
    api_key: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.3
    top_p: float = 0.3
    system_prompt: str | None = None
    theme: str = "catppuccin"

    def __post_init__(self) -> None:
        if not 0.0 <= self.temperature <= 2.0:
            raise ConfigError(f"temperature must be 0.0-2.0, got {self.temperature}")
        if self.max_tokens < 1:
            raise ConfigError(f"max_tokens must be >= 1, got {self.max_tokens}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        valid_keys = cls.__dataclass_fields__.keys()
        filtered = {}
        for k, v in data.items():
            if k not in valid_keys:
                continue
            # Treat empty string as None for string fields
            if isinstance(v, str) and not v:
                continue
            filtered[k] = v
        return cls(**filtered)

    @classmethod
    def from_yaml(cls, path: Path | str) -> Config:
        path_str = str(path)
        logger.info("Loading config from YAML: %s", path_str)
        with open(path) as f:
            data = yaml.safe_load(f)
        result = cls.from_dict(data or {})
        logger.debug("Config loaded from %s: provider=%s model=%s", path_str, result.provider, result.model)
        return result

    @classmethod
    def from_env(cls) -> Config | None:
        env_map: dict[str, str] = {}
        prefix = "CSCODE_"
        for key, val in os.environ.items():
            if key.startswith(prefix) and val:
                config_key = key[len(prefix) :].lower()
                if config_key in cls.__dataclass_fields__:
                    env_map[config_key] = val
        if not env_map:
            return None
        config = cls.from_dict(env_map)
        logger.debug("Config loaded from env: provider=%s model=%s", config.provider, config.model)
        return config

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result.pop("api_key", None)
        return {k: v for k, v in result.items() if v is not None and (not isinstance(v, str) or v)}

    def to_yaml(self, path: Path | str) -> None:
        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False)

    def merge(self, other: Config) -> Config:
        merged = asdict(self)
        for k, v in asdict(other).items():
            if v is None:
                continue
            if isinstance(v, str) and not v:
                continue
            merged[k] = v
        return Config(**merged)


def load_config(
    config_dirs: list[Path] | None = None,
    cli_overrides: dict[str, Any] | None = None,
    db_config: dict[str, Any] | None = None,
) -> Config:
    logger.debug("load_config: cli_overrides=%s db_config=%s", cli_overrides, "present" if db_config else "none")
    """Load config from multiple sources, in order of priority (lowest to highest):
    1. Default values
    2. YAML config files
    3. Environment variables
    4. Database (user saved config) - NEW
    5. CLI overrides
    """
    config = Config()

    if config_dirs is None:
        config_dirs = [
            Path.home() / ".config" / "cscode",
            Path.cwd() / ".cscode",
        ]

    for config_dir in config_dirs:
        yaml_path = config_dir / "config.yaml"
        if yaml_path.exists():
            config = config.merge(Config.from_yaml(yaml_path))

    env_config = Config.from_env()
    if env_config is not None:
        config = config.merge(env_config)

    # Database config has higher priority than file/env
    if db_config:
        config = config.merge(Config.from_dict(db_config))

    if cli_overrides:
        config = config.merge(Config.from_dict(cli_overrides))

    logger.info("Config loaded: provider=%s model=%s api_base=%s", config.provider, config.model, config.api_base or "default")
    return config


class ConfigStore:
    """Store and retrieve config from SQLite."""

    def __init__(self, db: Database):
        self.db = db

    async def get(self) -> dict[str, Any] | None:
        row = await self.db.fetchone(
            "SELECT data FROM config WHERE key = 'user_config'"
        )
        if row and row["data"]:
            import json
            data = json.loads(row["data"])
            logger.debug("Config loaded from DB: %s keys", list(data.keys()))
            return data  # type: ignore[no-any-return]
        logger.debug("No saved config found in DB")
        return None

    async def save(self, data: dict[str, Any]) -> None:
        import json
        logger.info("Config saved to DB: %s keys", list(data.keys()))
        data_json = json.dumps(data, default=str)
        await self.db.execute(
            """
            INSERT INTO config (key, data) VALUES ('user_config', ?)
            ON CONFLICT(key) DO UPDATE SET data = excluded.data
            """,
            (data_json,),
        )
