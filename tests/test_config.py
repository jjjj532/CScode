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
