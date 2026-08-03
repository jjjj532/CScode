from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cscode.core.config import Config, ConfigError, load_config


def test_default_config_values():
    """默认配置必须有合理的默认值"""
    config = Config()
    assert config.provider == "openai"
    assert config.model == "gpt-4o"
    assert config.max_tokens > 0
    assert config.temperature >= 0.0


def test_config_from_dict():
    """从字典加载配置"""
    cfg = Config.from_dict({
        "provider": "anthropic",
        "model": "claude-sonnet-4-5",
        "temperature": 0.5,
    })
    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-sonnet-4-5"
    assert cfg.temperature == 0.5
    assert cfg.max_tokens == 4096  # 默认值


def test_config_yaml_roundtrip(tmp_path: Path):
    """配置可以序列化到 YAML 并重新加载"""
    cfg = Config(
        provider="ollama",
        model="qwen2.5-coder:7b",
        api_base="http://localhost:11434",
    )
    yaml_path = tmp_path / "config.yaml"
    cfg.to_yaml(yaml_path)

    loaded = Config.from_yaml(yaml_path)
    assert loaded.provider == "ollama"
    assert loaded.model == "qwen2.5-coder:7b"
    assert loaded.api_base == "http://localhost:11434"


def test_load_config_cascade(tmp_path: Path):
    """配置级联：项目配置覆盖全局配置"""
    global_dir = tmp_path / "global"
    project_dir = tmp_path / "project"
    global_dir.mkdir()
    project_dir.mkdir()

    # 全局配置
    (global_dir / "config.yaml").write_text(yaml.dump({
        "provider": "openai",
        "model": "gpt-4o",
    }))
    # 项目配置覆盖 provider
    (project_dir / ".cscode").mkdir()
    (project_dir / ".cscode" / "config.yaml").write_text(yaml.dump({
        "provider": "anthropic",
    }))

    config = load_config(
        config_dirs=[global_dir, project_dir / ".cscode"],
    )
    assert config.provider == "anthropic"  # 项目覆盖全局
    assert config.model == "gpt-4o"  # 从全局继承


def test_config_env_override(monkeypatch: pytest.MonkeyPatch):
    """环境变量覆盖配置文件"""
    monkeypatch.setenv("CSCODE_PROVIDER", "ollama")
    monkeypatch.setenv("CSCODE_MODEL", "deepseek-coder-v2")

    cfg = Config.from_env()
    assert cfg is not None
    assert cfg.provider == "ollama"
    assert cfg.model == "deepseek-coder-v2"


def test_config_env_none_when_unset():
    """没有设置环境变量时 from_env 返回 None"""
    cfg = Config.from_env()
    assert cfg is None


def test_load_config_env_overrides_db(monkeypatch: pytest.MonkeyPatch):
    """BUG-003 retest: 运行时环境变量必须覆盖 DB 保存的用户配置。
    设计意图是 launchctl/launchd env 可作为运行时强制覆盖。
    """
    monkeypatch.setenv("CSCODE_MODEL", "env-override-model-X99")
    monkeypatch.setenv("CSCODE_API_BASE", "https://env-test.example.com/v99")

    db_config = {
        "provider": "openai",
        "model": "MiniMax-M2.5",
        "api_base": "https://api.scnet.cn/api/llm/v1",
        "api_key": "sk-db-saved-key",
    }
    cfg = load_config(db_config=db_config)
    assert cfg.model == "env-override-model-X99"
    assert cfg.api_base == "https://env-test.example.com/v99"
    # env 未设置的字段仍从 DB 继承
    assert cfg.api_key == "sk-db-saved-key"
    assert cfg.provider == "openai"


def test_load_config_db_when_env_unset(db_config: dict[str, str] | None = None):
    """没有设置环境变量时，DB 配置正常生效（UI 保存不被覆盖）。"""
    db_cfg = {
        "provider": "anthropic",
        "model": "claude-sonnet-4-5",
        "api_base": "https://api.anthropic.com",
    }
    cfg = load_config(db_config=db_cfg)
    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-sonnet-4-5"
    assert cfg.api_base == "https://api.anthropic.com"


def test_load_config_cli_overrides_env(monkeypatch: pytest.MonkeyPatch):
    """CLI 优先级最高，覆盖 env。"""
    monkeypatch.setenv("CSCODE_MODEL", "env-model")
    cfg = load_config(db_config=None, cli_overrides={"model": "cli-model"})
    assert cfg.model == "cli-model"


def test_load_config_env_does_not_clobber_db_defaults(monkeypatch: pytest.MonkeyPatch):
    """已知问题修复: env 只覆盖显式设置的字段，DB 保存的其他字段
    （如 temperature/max_tokens）不被 env Config 的 dataclass 默认值覆盖。
    """
    monkeypatch.setenv("CSCODE_MODEL", "env-model")
    db_config = {
        "provider": "openai",
        "model": "gpt-4o",
        "temperature": 0.55,
        "max_tokens": 8192,
    }
    cfg = load_config(db_config=db_config)
    assert cfg.model == "env-model"  # env 覆盖 model
    assert cfg.temperature == 0.55  # DB 的 temperature 保留（不被 env 默认 0.3 覆盖）
    assert cfg.max_tokens == 8192  # DB 的 max_tokens 保留


def test_from_dict_filters_empty_string():
    """BUG-003: from_dict treats empty string as None (frontend sends '' for unset fields).
    Regression test: empty strings must NOT overwrite defaults.
    """
    cfg = Config.from_dict({
        "provider": "",
        "model": "",
        "api_base": "",
        "system_prompt": "",
    })
    assert cfg.provider == "openai"
    assert cfg.model == "gpt-4o"
    assert cfg.api_base is None
    assert cfg.system_prompt is None


def test_merge_filters_empty_string():
    """BUG-003: merge treats empty string as None.
    Regression test: merging a config with empty strings must NOT overwrite existing values.
    """
    base = Config(provider="anthropic", model="claude-sonnet-4-5", api_base="https://api.anthropic.com")
    # Construct a Config with empty strings directly (simulates what from_dict would
    # produce if the empty-string filter were absent)
    override = Config(provider="", model="", api_base="")
    merged = base.merge(override)
    assert merged.provider == "anthropic"
    assert merged.model == "claude-sonnet-4-5"
    assert merged.api_base == "https://api.anthropic.com"


def test_to_dict_excludes_empty_string():
    """BUG-003: to_dict excludes empty strings (not just None).
    Regression test: to_dict must not return fields with empty string values.
    """
    cfg = Config(provider="openai", api_base="", system_prompt="")
    d = cfg.to_dict()
    assert "api_key" not in d
    assert "api_base" not in d
    assert "system_prompt" not in d
    assert d.get("provider") == "openai"


def test_invalid_temperature():
    """无效的 temperature 应该报错"""
    with pytest.raises(ConfigError):
        Config.from_dict({"temperature": 2.5})


def test_config_contains_api_keys():
    """API Key 存储但不会序列化到明文"""
    cfg = Config(api_key="sk-test123")
    assert cfg.api_key == "sk-test123"

    yaml_str = yaml.dump(cfg.to_dict())
    assert "sk-test123" not in yaml_str


# ─── Slice 0.3: Variable substitution ─────────────────────────────────────


def test_variable_subst_env():
    """S0.3.4: ${env.HOME} resolves to the HOME env var."""
    from cscode.core.config_variable import resolve_variables
    result = resolve_variables("${env.HOME}")
    import os
    assert result == os.environ.get("HOME", "")


def test_variable_subst_unknown_env():
    """S0.3.4: ${env.UNKNOWN_VAR_XYZ} resolves to empty string."""
    from cscode.core.config_variable import resolve_variables
    result = resolve_variables("${env.UNKNOWN_VAR_XYZ}")
    assert result == ""


def test_variable_subst_in_config_value():
    """S0.3.4: Variable substitution in a config value."""
    from cscode.core.config_variable import resolve_config
    cfg = {"api_base": "http://localhost:${env.PORT:-8080}"}
    result = resolve_config(cfg)
    assert result["api_base"] == "http://localhost:8080"


def test_variable_subst_default():
    """S0.3.4: ${env.VAR:-default} falls back to default."""
    from cscode.core.config_variable import resolve_variables
    result = resolve_variables("${env.MISSING_VAR_XYZ:-default_val}")
    assert result == "default_val"


def test_variable_no_subst():
    """S0.3.4: String without variable syntax is returned as-is."""
    from cscode.core.config_variable import resolve_variables
    result = resolve_variables("just a plain string")
    assert result == "just a plain string"


# ─── Slice 0.3: Config scanner ──────────────────────────────────────────


def test_scan_no_config_files(tmp_path: Path):
    """S0.3.1: scan_config returns empty list when no config files exist."""
    from cscode.core.config_scanner import scan_config
    result = scan_config(search_dirs=[tmp_path])
    assert result == []


def test_scan_discovers_yaml(tmp_path: Path):
    """S0.3.1: scan_config discovers .yaml config files."""
    from cscode.core.config_scanner import scan_config
    d = tmp_path / ".cscode"
    d.mkdir(parents=True)
    (d / "config.yaml").write_text("provider: anthropic\n")
    result = scan_config(search_dirs=[d])
    assert len(result) == 1
    assert result[0].path == d / "config.yaml"
    assert result[0].layer == "project"


def test_scan_discovers_json(tmp_path: Path):
    """S0.3.1: scan_config discovers .json config files via local_dirs."""
    from cscode.core.config_scanner import scan_config
    d = tmp_path / ".opencode"
    d.mkdir(parents=True)
    (d / "config.json").write_text('{"provider": "anthropic"}\n')
    result = scan_config(local_dirs=[d])
    assert len(result) == 1
    assert result[0].path == d / "config.json"
    assert result[0].layer == "local"


def test_scan_layers_priority(tmp_path: Path):
    """S0.3.1: Layers are ordered global < project < local."""
    from cscode.core.config_scanner import scan_config
    # search_dirs: layer="global" for plain dirs, "project" when path has ".cscode"
    global_d = tmp_path / "global"
    project_d = tmp_path / "project" / ".cscode"
    local_d = tmp_path / "local"
    for d in (global_d, project_d, local_d):
        d.mkdir(parents=True)
    (global_d / "config.yaml").write_text("")
    (project_d / "config.yaml").write_text("")
    (local_d / "config.yaml").write_text("")
    result = scan_config(
        search_dirs=[global_d, project_d],
        local_dirs=[local_d],
    )
    layers = [r.layer for r in result]
    assert layers == ["global", "project", "local"]


def test_load_config_uses_scanner(tmp_path: Path):
    """S0.3.5: load_config uses config_scanner to discover files."""
    from cscode.core.config_scanner import load_config_from_layers
    global_d = tmp_path / "global" / ".cscode"
    global_d.mkdir(parents=True)
    (global_d / "config.yaml").write_text("provider: openai\nmodel: gpt-4o\n")
    project_d = tmp_path / "project" / ".cscode"
    project_d.mkdir(parents=True)
    (project_d / "config.yaml").write_text("model: gpt-4o-mini\n")
    cfg = load_config_from_layers(search_dirs=[global_d, project_d])
    assert cfg.provider == "openai"
    assert cfg.model == "gpt-4o-mini"
