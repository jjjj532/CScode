"""ConfigV2 — 结构化多层配置，对标 OpenCode 配置模型。

Usage:
    cfg = ConfigV2.load()
    cfg.model.provider  # "openai"
    cfg.shell.shell     # "/bin/bash"

层层合并顺序 (低→高优先级):
    1. ConfigV2 默认值
    2. 全局配置 (~/.config/cscode/config.yaml)
    3. 项目配置 (<project>/.cscode/config.yaml)
    4. 本地配置 (<project>/.opencode/config.yaml)
    5. 数据库配置
    6. CLI 覆盖

向后兼容:
    legacy = cfg.to_legacy()       # ConfigV2 → Config
    v2 = ConfigV2.from_legacy(cfg) # Config → ConfigV2
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cscode.core.config_variable import resolve_config
from cscode.core.errors import ConfigError
from cscode.core.permission_v2 import Rule, RuleEffect, Ruleset
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


# ─── Sub-config types ────────────────────────────────────────────────


@dataclass
class ShellConfig:
    """Shell 配置。"""

    shell: str = "/bin/bash"
    timezone: str | None = None


@dataclass
class ModelConfig:
    """模型配置 (单模型实例)。"""

    provider: str = "openai"
    model: str = "gpt-4o"
    api_base: str | None = None
    api_key: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.3
    top_p: float = 0.3

    def __post_init__(self) -> None:
        if not 0.0 <= self.temperature <= 2.0:
            msg = f"temperature must be 0.0-2.0, got {self.temperature}"
            raise ConfigError(msg)
        if self.max_tokens < 1:
            msg = f"max_tokens must be >= 1, got {self.max_tokens}"
            raise ConfigError(msg)


@dataclass
class AgentConfig:
    """Agent 行为配置。"""

    system_prompt: str | None = None
    max_tool_rounds: int = 20


@dataclass
class MCPConfig:
    """MCP server 配置。"""

    name: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class PluginConfig:
    """插件配置。"""

    name: str = ""
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderConfig:
    """Provider 级联配置 (用于多 provider 场景)。"""

    api_key: str | None = None
    api_base: str | None = None


# ─── ConfigV2 ────────────────────────────────────────────────────────


def _is_not_empty(val: Any) -> bool:
    """Return True if *val* is considered 'set' (not None, not empty string)."""
    if val is None:
        return False
    if isinstance(val, str) and not val:
        return False
    return True


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge *override* into *base*.

    Only non-None/non-empty values from *override* replace values in *base*.
    Nested dicts are merged recursively.
    """
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and k in result and isinstance(result[k], dict):
            result[k] = _merge_dict(result[k], v)
        elif _is_not_empty(v):
            result[k] = v
    return result


@dataclass
class ConfigV2:
    """结构化多子段配置。

    Fields:
        shell: Shell 配置 (可选).
        model: 默认模型配置 (可选，不设时用 ModelConfig 默认).
        agent: 按名称索引的 Agent 配置.
        permissions: 权限规则列表 (Ruleset).
        mcp: MCP server 配置列表.
        plugin: 插件配置列表.
        provider: 按 provider 名称索引的级联配置.
    """

    shell: ShellConfig | None = None
    model: ModelConfig = field(default_factory=ModelConfig)
    agent: dict[str, AgentConfig] = field(default_factory=dict)
    permissions: list[Ruleset] = field(default_factory=list)
    mcp: list[MCPConfig] = field(default_factory=list)
    plugin: list[PluginConfig] = field(default_factory=list)
    provider: dict[str, ProviderConfig] = field(default_factory=dict)

    # ─── Serialisation ──────────────────────────────────────────────

    def to_dict(self, *, include_secrets: bool = False) -> dict[str, Any]:
        """Flatten to a dict (excluding API keys by default)."""
        result: dict[str, Any] = {}
        if self.shell is not None:
            d = {"shell": self.shell.shell}
            if self.shell.timezone:
                d["timezone"] = self.shell.timezone
            result["shell"] = d
        if self.model is not None:
            md: dict[str, Any] = {
                "provider": self.model.provider,
                "model": self.model.model,
                "max_tokens": self.model.max_tokens,
                "temperature": self.model.temperature,
                "top_p": self.model.top_p,
            }
            if self.model.api_base:
                md["api_base"] = self.model.api_base
            if include_secrets and self.model.api_key:
                md["api_key"] = self.model.api_key
            result["model"] = md
        if self.agent:
            result["agent"] = {name: {"system_prompt": a.system_prompt, "max_tool_rounds": a.max_tool_rounds} for name, a in self.agent.items()}
        if self.permissions:
            result["permissions"] = [
                {"name": rs.name, "rules": [{"action": r.action, "resource": r.resource, "effect": r.effect.value} for r in rs.rules]}
                for rs in self.permissions
            ]
        if self.mcp:
            result["mcp"] = [{"name": m.name, "command": m.command, "args": m.args, "env": m.env} for m in self.mcp]
        if self.plugin:
            result["plugin"] = [{"name": p.name, "enabled": p.enabled, "config": p.config} for p in self.plugin]
        if self.provider:
            result["provider"] = {name: {"api_base": p.api_base} for name, p in self.provider.items() if p.api_base}
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConfigV2:
        """Parse a nested dict into ConfigV2.

        Expected structure:
            {
                "shell": {"shell": "/bin/zsh", "timezone": "Asia/Shanghai"},
                "model": {"provider": "openai", "model": "gpt-4o", ...},
                "agent": {"default": {"system_prompt": "...", ...}},
                "permissions": [{"name": "...", "rules": [...]}],
                "mcp": [{"name": "...", "command": "..."}],
                "plugin": [{"name": "...", "enabled": true}],
                "provider": {"openai": {"api_base": "..."}},
            }
        """
        cfg = cls()

        # Shell
        shell_data = data.get("shell")
        if isinstance(shell_data, dict):
            cfg.shell = ShellConfig(
                shell=str(shell_data.get("shell", "/bin/bash")),
                timezone=shell_data.get("timezone"),
            )

        # Model
        model_data = data.get("model")
        if isinstance(model_data, dict):
            cfg.model = ModelConfig(
                provider=str(model_data.get("provider", "openai")),
                model=str(model_data.get("model", "gpt-4o")),
                api_base=model_data.get("api_base"),
                api_key=model_data.get("api_key"),
                max_tokens=int(model_data.get("max_tokens", 4096)),
                temperature=float(model_data.get("temperature", 0.3)),
                top_p=float(model_data.get("top_p", 0.3)),
            )

        # Agent map
        agent_data = data.get("agent")
        if isinstance(agent_data, dict):
            for name, ac in agent_data.items():
                if isinstance(ac, dict):
                    cfg.agent[name] = AgentConfig(
                        system_prompt=ac.get("system_prompt"),
                        max_tool_rounds=int(ac.get("max_tool_rounds", 20)),
                    )

        # Permissions
        perm_list = data.get("permissions")
        if isinstance(perm_list, list):
            for rs_item in perm_list:
                if not isinstance(rs_item, dict):
                    continue
                rules_raw = rs_item.get("rules", [])
                rules: list[Rule] = []
                if isinstance(rules_raw, list):
                    for r in rules_raw:
                        if isinstance(r, dict):
                            rules.append(Rule(
                                action=str(r.get("action", "*")),
                                resource=str(r.get("resource", "*")),
                                effect=RuleEffect(r.get("effect", "deny")),
                            ))
                cfg.permissions.append(Ruleset(
                    name=str(rs_item.get("name", "")),
                    rules=rules,
                ))

        # MCP
        mcp_list = data.get("mcp")
        if isinstance(mcp_list, list):
            for m in mcp_list:
                if isinstance(m, dict):
                    cfg.mcp.append(MCPConfig(
                        name=str(m.get("name", "")),
                        command=str(m.get("command", "")),
                        args=list(m.get("args", [])),
                        env=dict(m.get("env", {})),
                    ))

        # Plugin
        plugin_list = data.get("plugin")
        if isinstance(plugin_list, list):
            for p in plugin_list:
                if isinstance(p, dict):
                    cfg.plugin.append(PluginConfig(
                        name=str(p.get("name", "")),
                        enabled=bool(p.get("enabled", True)),
                        config=dict(p.get("config", {})),
                    ))

        # Provider
        provider_data = data.get("provider")
        if isinstance(provider_data, dict):
            for name, pd in provider_data.items():
                if isinstance(pd, dict):
                    cfg.provider[name] = ProviderConfig(
                        api_key=pd.get("api_key"),
                        api_base=pd.get("api_base"),
                    )

        return cfg

    # ─── Backward compat ────────────────────────────────────────────

    def to_legacy(self) -> Any:
        """Convert to legacy ``cscode.core.config.Config``."""
        from cscode.core.config import Config as LegacyConfig

        kwargs: dict[str, Any] = {}
        if self.model is not None:
            kwargs["provider"] = self.model.provider
            kwargs["model"] = self.model.model
            kwargs["api_base"] = self.model.api_base or ""
            kwargs["api_key"] = self.model.api_key
            kwargs["max_tokens"] = self.model.max_tokens
            kwargs["temperature"] = self.model.temperature
            kwargs["top_p"] = self.model.top_p
        # System prompt from default agent config
        if "default" in self.agent and self.agent["default"].system_prompt:
            kwargs["system_prompt"] = self.agent["default"].system_prompt
        return LegacyConfig(**kwargs)

    @classmethod
    def from_legacy(cls, legacy: Any) -> ConfigV2:
        """Convert from legacy ``cscode.core.config.Config``."""
        model = ModelConfig(
            provider=getattr(legacy, "provider", "openai"),
            model=getattr(legacy, "model", "gpt-4o"),
            api_base=getattr(legacy, "api_base", None),
            api_key=getattr(legacy, "api_key", None),
            max_tokens=getattr(legacy, "max_tokens", 4096),
            temperature=getattr(legacy, "temperature", 0.3),
            top_p=getattr(legacy, "top_p", 0.3),
        )
        agent: dict[str, AgentConfig] = {}
        sp = getattr(legacy, "system_prompt", None)
        if sp:
            agent["default"] = AgentConfig(system_prompt=sp)
        return cls(model=model, agent=agent)

    # ─── Loading ────────────────────────────────────────────────────

    @classmethod
    def load(
        cls,
        search_dirs: list[Path] | None = None,
        local_dirs: list[Path] | None = None,
        cli_overrides: dict[str, Any] | None = None,
        db_config: dict[str, Any] | None = None,
    ) -> ConfigV2:
        """Load config using the three-layer scanner.

        Args:
            search_dirs: Directories to scan for global/project config.
            local_dirs: Directories to scan for local config (highest file priority).
            cli_overrides: CLI-provided overrides (highest priority).
            db_config: Database-persisted overrides.

        Returns:
            A fully merged ConfigV2.
        """
        from cscode.core.config_scanner import scan_config

        if search_dirs is None and local_dirs is None:
            home = Path.home() / ".config" / "cscode"
            from cscode.core.config_scanner import find_project_root
            project_root = find_project_root()
            search_dirs = [home]
            if project_root:
                search_dirs.append(project_root / ".cscode")
            local_dirs = [project_root / ".opencode"] if project_root else []

        sources = scan_config(search_dirs=search_dirs, local_dirs=local_dirs)

        # Start from defaults, overlay file sources
        cfg = cls()
        for src in sources:
            data = src.load()
            resolved = resolve_config(data)
            overlay = cls.from_dict(resolved)
            cfg = cfg.merge(overlay)

        # Environment variables (above file layers, below DB/CLI)
        env_cfg = _config_v2_from_env()
        if env_cfg is not None:
            cfg = cfg.merge(env_cfg)

        # DB + CLI overrides
        if db_config:
            cfg = cfg.merge(cls.from_dict(db_config))
        if cli_overrides:
            cfg = cfg.merge(cls.from_dict(cli_overrides))

        logger.info(
            "ConfigV2 loaded: model=%s/%s",
            cfg.model.provider if cfg.model else "?",
            cfg.model.model if cfg.model else "?",
        )
        return cfg

    # ─── Merging ────────────────────────────────────────────────────

    def merge(self, other: ConfigV2) -> ConfigV2:
        """Merge *other* into *self*, with *other* taking priority.

        Rules:
            - Scalar fields (shell, model): *other*'s value wins if not None.
            - Dict fields (agent, provider): deep-merged.
            - List fields (permissions, mcp, plugin): *other*'s list replaces.
        """
        # Shell (scalar replacement)
        shell = other.shell if other.shell is not None else self.shell

        # Model (scalar replacement)
        model = other.model if other.model is not None else self.model

        # Dict fields — deep merge
        agent = _merge_dict(self.agent, other.agent)
        provider = _merge_dict(self.provider, other.provider)

        # List fields — replace
        permissions = list(other.permissions) if other.permissions else list(self.permissions)
        mcp = list(other.mcp) if other.mcp else list(self.mcp)
        plugin = list(other.plugin) if other.plugin else list(self.plugin)

        return ConfigV2(
            shell=shell,
            model=model,
            agent=agent,
            permissions=permissions,
            mcp=mcp,
            plugin=plugin,
            provider=provider,
        )


# ─── Internal helpers ────────────────────────────────────────────────


def _config_v2_from_env() -> ConfigV2 | None:
    """Build a partial ConfigV2 from CSCODE_* environment variables.

    Only CSCODE_* vars that match a LegacyConfig field name produce
    a ConfigV2 (field names are lowercase: ``CSCODE_PROVIDER`` →
    ``provider``). Returns ``None`` when no recognised variables
    are found.
    """
    from cscode.core.config import Config as LegacyConfig

    valid_keys = LegacyConfig.__dataclass_fields__.keys()
    env_map: dict[str, str] = {}
    prefix = "CSCODE_"
    for key, val in os.environ.items():
        if key.startswith(prefix) and val:
            config_key = key[len(prefix):].lower()
            if config_key in valid_keys:
                env_map[config_key] = val
    if not env_map:
        return None

    legacy = LegacyConfig.from_dict(env_map)
    return ConfigV2.from_legacy(legacy)
