"""ConfigV2 — 结构化多层配置 TDD (RED: 所有测试应先失败).

ConfigV2 对标 OpenCode 的结构化配置:
- 多子配置段 (shell / model / agent / permissions / mcp / plugin / provider)
- 三层合并: global → project → local
- 向后兼容: ConfigV2 ↔ 旧 Config 互转
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from cscode.core.permission_v2 import Rule, RuleEffect, Ruleset


# ─── RED 1: 默认值 ──────────────────────────────────────────────────


def test_default_config_v2() -> None:
    """ConfigV2 有合理的默认值."""
    from cscode.core.config_v2 import ConfigV2, ModelConfig

    cfg = ConfigV2()
    assert cfg.model is not None
    assert cfg.model.provider == "openai"
    assert cfg.model.model == "gpt-4o"
    assert cfg.model.max_tokens == 4096
    assert cfg.model.temperature == 0.3

    # 可选子段默认 None
    assert cfg.shell is None
    assert cfg.agent == {}
    assert cfg.permissions == []
    assert cfg.mcp == []
    assert cfg.plugin == []
    assert cfg.provider == {}


# ─── RED 2: 三层加载与合并 ───────────────────────────────────────


def test_load_merges_global_then_project(tmp_path: Path) -> None:
    """ConfigV2.load() 合并全局 → 项目配置: 项目覆盖全局."""
    from cscode.core.config_v2 import ConfigV2

    global_dir = tmp_path / "global"
    project_dir = tmp_path / "project"
    global_dir.mkdir(parents=True)
    project_dir.mkdir(parents=True)

    (global_dir / "config.yaml").write_text(yaml.dump({
        "model": {"provider": "openai", "model": "gpt-4o"},
    }))
    (project_dir / "config.yaml").write_text(yaml.dump({
        "model": {"model": "gpt-4o-mini"},
    }))

    cfg = ConfigV2.load(search_dirs=[global_dir, project_dir])
    assert cfg.model is not None
    assert cfg.model.provider == "openai"  # 从全局继承
    assert cfg.model.model == "gpt-4o-mini"  # 被项目覆盖


def test_load_merges_local_over_project(tmp_path: Path) -> None:
    """本地配置 (local) 优先级高于项目配置."""
    from cscode.core.config_v2 import ConfigV2

    project_dir = tmp_path / "project"
    local_dir = tmp_path / "local"
    project_dir.mkdir(parents=True)
    local_dir.mkdir(parents=True)

    (project_dir / "config.yaml").write_text(yaml.dump({
        "model": {"provider": "openai", "model": "gpt-4o"},
    }))
    (local_dir / "config.yaml").write_text(yaml.dump({
        "model": {"model": "claude-sonnet-4-5"},
    }))

    cfg = ConfigV2.load(search_dirs=[project_dir], local_dirs=[local_dir])
    assert cfg.model is not None
    assert cfg.model.provider == "openai"
    assert cfg.model.model == "claude-sonnet-4-5"  # local 覆盖 project


# ─── RED 3: 子配置段 ────────────────────────────────────────────────


def test_shell_config() -> None:
    """ConfigV2 支持 shell 子配置."""
    from cscode.core.config_v2 import ConfigV2, ShellConfig

    cfg = ConfigV2(shell=ShellConfig(shell="/bin/zsh", timezone="Asia/Shanghai"))
    assert cfg.shell is not None
    assert cfg.shell.shell == "/bin/zsh"
    assert cfg.shell.timezone == "Asia/Shanghai"


def test_agent_config_map() -> None:
    """ConfigV2 支持多个 agent 配置."""
    from cscode.core.config_v2 import AgentConfig, ConfigV2

    cfg = ConfigV2(agent={
        "default": AgentConfig(system_prompt="You are helpful", max_tool_rounds=20),
        "coder": AgentConfig(system_prompt="You are a coder", max_tool_rounds=50),
    })
    assert len(cfg.agent) == 2
    assert cfg.agent["default"].max_tool_rounds == 20
    assert cfg.agent["coder"].max_tool_rounds == 50


def test_mcp_config_list() -> None:
    """ConfigV2 支持 MCP server 配置列表."""
    from cscode.core.config_v2 import ConfigV2, MCPConfig

    cfg = ConfigV2(mcp=[
        MCPConfig(name="filesystem", command="npx", args=["-y", "@modelcontextprotocol/server-filesystem"]),
    ])
    assert len(cfg.mcp) == 1
    assert cfg.mcp[0].name == "filesystem"
    assert cfg.mcp[0].command == "npx"


def test_permission_rules_integration() -> None:
    """ConfigV2 直接使用 PermissionV2 的 Rule/Ruleset."""
    from cscode.core.config_v2 import ConfigV2

    ruleset = Ruleset(name="safe", rules=[
        Rule(action="*", resource="*", effect=RuleEffect.ALLOW),
        Rule(action="bash", resource="/etc/*", effect=RuleEffect.DENY),
    ])
    cfg = ConfigV2(permissions=[ruleset])
    assert len(cfg.permissions) == 1
    assert cfg.permissions[0].name == "safe"


# ─── RED 4: 向后兼容 ────────────────────────────────────────────────


def test_to_legacy_config() -> None:
    """ConfigV2 → 旧 Config 转换."""
    from cscode.core.config_v2 import ConfigV2, ModelConfig

    v2 = ConfigV2(model=ModelConfig(provider="anthropic", model="claude-sonnet-4-5", api_key="sk-test"))
    legacy = v2.to_legacy()
    assert legacy.provider == "anthropic"
    assert legacy.model == "claude-sonnet-4-5"
    assert legacy.api_key == "sk-test"
    assert legacy.max_tokens == 4096  # 默认值
    assert legacy.temperature == 0.3


def test_from_legacy_config() -> None:
    """旧 Config → ConfigV2 转换."""
    from cscode.core.config_v2 import ConfigV2
    from cscode.core.config import Config

    legacy = Config(provider="ollama", model="qwen2.5-coder:7b", api_base="http://localhost:11434")
    v2 = ConfigV2.from_legacy(legacy)
    assert v2.model is not None
    assert v2.model.provider == "ollama"
    assert v2.model.model == "qwen2.5-coder:7b"
    assert v2.model.api_base == "http://localhost:11434"


# ─── RED 5: 变量解析集成 ────────────────────────────────────────────


def test_variable_subst_in_config_v2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ConfigV2.load() 支持 ${env.VAR} 变量替换."""
    from cscode.core.config_v2 import ConfigV2

    monkeypatch.setenv("CSCODE_TEST_MODEL", "claude-sonnet-4-5")
    d = tmp_path / "cfg"
    d.mkdir(parents=True)
    (d / "config.yaml").write_text(yaml.dump({
        "model": {"model": "${env.CSCODE_TEST_MODEL}"},
    }))

    cfg = ConfigV2.load(search_dirs=[d])
    assert cfg.model is not None
    assert cfg.model.model == "claude-sonnet-4-5"
