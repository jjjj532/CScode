"""Tests for Config sub-modules (experimental, formatter, markdown, tool-output, lsp, reference)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pytest

from cscode.core.config import (
    Config,
    ExperimentalConfig,
    FormatterConfig,
    MarkdownConfig,
    ToolOutputConfig,
    LSPConfig,
    ReferenceConfig,
)


class TestExperimentalConfig:
    def test_defaults(self) -> None:
        """ExperimentalConfig should have sensible defaults."""
        ec = ExperimentalConfig()
        assert ec.tools_v2 is False
        assert ec.streaming is True
        assert ec.mcp is False

    def test_from_dict(self) -> None:
        ec = ExperimentalConfig.from_dict({"tools_v2": True, "streaming": False})
        assert ec.tools_v2 is True
        assert ec.streaming is False
        assert ec.mcp is False  # default

    def test_from_dict_empty(self) -> None:
        ec = ExperimentalConfig.from_dict({})
        assert ec == ExperimentalConfig()

    def test_from_dict_ignores_unknown(self) -> None:
        ec = ExperimentalConfig.from_dict({"tools_v2": True, "unknown_key": "foo"})
        assert ec.tools_v2 is True

    def test_to_dict_excludes_none(self) -> None:
        ec = ExperimentalConfig(tools_v2=True)
        d = ec.to_dict()
        assert d.get("tools_v2") is True
        assert "streaming" not in d or d["streaming"] is not False  # False is meaningful

    def test_merge_overrides(self) -> None:
        base = ExperimentalConfig(tools_v2=False, streaming=True, mcp=False)
        override = ExperimentalConfig(streaming=False)
        merged = base.merge(override)
        assert merged.tools_v2 is False
        assert merged.streaming is False  # overridden
        assert merged.mcp is False


class TestFormatterConfig:
    def test_defaults(self) -> None:
        fc = FormatterConfig()
        assert fc.enabled is True
        assert fc.line_length == 88
        assert fc.python == "ruff"

    def test_from_dict_partial(self) -> None:
        fc = FormatterConfig.from_dict({"enabled": False})
        assert fc.enabled is False
        assert fc.line_length == 88
        assert fc.python == "ruff"

    def test_from_dict_full(self) -> None:
        fc = FormatterConfig.from_dict({
            "enabled": True,
            "line_length": 120,
            "python": "black",
            "javascript": "prettier",
        })
        assert fc.line_length == 120
        assert fc.python == "black"
        assert fc.javascript == "prettier"

    def test_merge(self) -> None:
        base = FormatterConfig(line_length=88)
        override = FormatterConfig(line_length=120, python="black")
        merged = base.merge(override)
        assert merged.line_length == 120
        assert merged.python == "black"


class TestMarkdownConfig:
    def test_defaults(self) -> None:
        mc = MarkdownConfig()
        assert mc.render is True
        assert mc.line_wrapping is True

    def test_from_dict(self) -> None:
        mc = MarkdownConfig.from_dict({"render": False, "line_wrapping": False})
        assert mc.render is False
        assert mc.line_wrapping is False


class TestToolOutputConfig:
    def test_defaults(self) -> None:
        tc = ToolOutputConfig()
        assert tc.max_chars == 10000
        assert tc.truncation_message == "[truncated]"

    def test_from_dict(self) -> None:
        tc = ToolOutputConfig.from_dict({"max_chars": 5000})
        assert tc.max_chars == 5000
        assert tc.truncation_message == "[truncated]"


class TestLSPConfig:
    def test_defaults(self) -> None:
        lc = LSPConfig()
        assert lc.enabled is True
        assert lc.diagnostics is True
        assert lc.code_actions is True

    def test_from_dict(self) -> None:
        lc = LSPConfig.from_dict({"enabled": False, "diagnostics": True, "code_actions": False})
        assert lc.enabled is False
        assert lc.diagnostics is True
        assert lc.code_actions is False


class TestReferenceConfig:
    def test_defaults(self) -> None:
        rc = ReferenceConfig()
        assert rc.max_results == 5
        assert rc.include_snippets is True

    def test_from_dict(self) -> None:
        rc = ReferenceConfig.from_dict({"max_results": 10, "include_snippets": False})
        assert rc.max_results == 10
        assert rc.include_snippets is False


# --- Integration with Config ---


class TestConfigSubModules:
    def test_config_can_hold_sub_configs(self) -> None:
        """Config should have optional sub-config fields."""
        c = Config()
        assert c.experimental is None
        assert c.formatter is None
        assert c.markdown is None
        assert c.tool_output is None
        assert c.lsp is None
        assert c.reference is None

    def test_config_with_experimental(self) -> None:
        ec = ExperimentalConfig(tools_v2=True)
        c = Config(experimental=ec)
        assert c.experimental is not None
        assert c.experimental.tools_v2 is True

    def test_from_dict_with_sub_configs(self) -> None:
        data: dict[str, Any] = {
            "provider": "anthropic",
            "experimental": {"tools_v2": True, "streaming": False},
            "formatter": {"line_length": 120, "python": "black"},
        }
        c = Config.from_dict(data)
        assert c.provider == "anthropic"
        assert c.experimental is not None
        assert c.experimental.tools_v2 is True
        assert c.experimental.streaming is False
        assert c.formatter is not None
        assert c.formatter.line_length == 120
        assert c.formatter.python == "black"

    def test_from_dict_ignores_unknown_sub_keys(self) -> None:
        data: dict[str, Any] = {
            "experimental": {"tools_v2": True, "bogus": "value"},
        }
        c = Config.from_dict(data)
        assert c.experimental is not None
        assert c.experimental.tools_v2 is True
        # bogus field is ignored silently

    def test_to_dict_includes_sub_configs(self) -> None:
        c = Config(
            experimental=ExperimentalConfig(tools_v2=True),
            formatter=FormatterConfig(line_length=120),
        )
        d = c.to_dict()
        assert d.get("provider") == "openai"
        assert "experimental" in d
        assert d["experimental"]["tools_v2"] is True
        assert "formatter" in d
        assert d["formatter"]["line_length"] == 120

    def test_to_dict_omits_none_sub_configs(self) -> None:
        c = Config()
        d = c.to_dict()
        assert d.get("experimental") is None  # None fields removed

    def test_merge_none_and_sub_config(self) -> None:
        """Merging a config with None sub-config into one with sub-config keeps the sub-config."""
        base = Config(experimental=ExperimentalConfig(tools_v2=True))
        override = Config()
        merged = base.merge(override)
        assert merged.experimental is not None
        assert merged.experimental.tools_v2 is True

    def test_merge_sub_config_overrides(self) -> None:
        """Merging should deep-merge sub-configs."""
        base = Config(
            experimental=ExperimentalConfig(tools_v2=False, streaming=True),
            formatter=FormatterConfig(line_length=88),
        )
        override = Config(
            experimental=ExperimentalConfig(tools_v2=True),  # override tools_v2, keep streaming
            formatter=FormatterConfig(line_length=120, python="black"),
        )
        merged = base.merge(override)
        # experimental deep merge
        assert merged.experimental is not None
        assert merged.experimental.tools_v2 is True  # overridden
        assert merged.experimental.streaming is True  # preserved from base
        # formatter deep merge
        assert merged.formatter is not None
        assert merged.formatter.line_length == 120
        assert merged.formatter.python == "black"

    def test_merge_sub_config_partial_override(self) -> None:
        """Only the specified sub-config fields should be overridden."""
        base = Config(
            lsp=LSPConfig(enabled=True, diagnostics=True, code_actions=True),
            reference=ReferenceConfig(max_results=5, include_snippets=True),
        )
        override = Config(
            lsp=LSPConfig(enabled=False),  # only change enabled
        )
        merged = base.merge(override)
        assert merged.lsp is not None
        assert merged.lsp.enabled is False
        assert merged.lsp.diagnostics is True  # preserved
        assert merged.lsp.code_actions is True  # preserved
        assert merged.reference is not None
        assert merged.reference.max_results == 5

    def test_from_dict_rich_yaml(self) -> None:
        """Simulate realistic YAML loading with all sub-configs."""
        data: dict[str, Any] = {
            "provider": "anthropic",
            "model": "claude-sonnet-4-20250514",
            "experimental": {"tools_v2": True, "mcp": True},
            "formatter": {"line_length": 100, "python": "ruff"},
            "markdown": {"render": True, "line_wrapping": True},
            "tool_output": {"max_chars": 20000},
            "lsp": {"enabled": True, "diagnostics": True, "code_actions": True},
            "reference": {"max_results": 10, "include_snippets": True},
        }
        c = Config.from_dict(data)
        assert c.provider == "anthropic"
        assert c.model == "claude-sonnet-4-20250514"
        assert c.experimental is not None and c.experimental.tools_v2 is True
        assert c.formatter is not None and c.formatter.line_length == 100
        assert c.markdown is not None and c.markdown.render is True
        assert c.tool_output is not None and c.tool_output.max_chars == 20000
        assert c.lsp is not None and c.lsp.enabled is True
        assert c.reference is not None and c.reference.max_results == 10

    def test_roundtrip_sub_configs(self) -> None:
        """to_dict -> from_dict should preserve sub-config values."""
        original = Config(
            experimental=ExperimentalConfig(tools_v2=True, mcp=True),
            formatter=FormatterConfig(line_length=120, python="black"),
            reference=ReferenceConfig(max_results=10),
        )
        d = original.to_dict()
        restored = Config.from_dict(d)
        assert restored.experimental is not None
        assert restored.experimental.tools_v2 == original.experimental.tools_v2
        assert restored.experimental.mcp == original.experimental.mcp
        assert restored.formatter is not None
        assert restored.formatter.line_length == original.formatter.line_length
        assert restored.formatter.python == original.formatter.python
        assert restored.reference is not None
        assert restored.reference.max_results == original.reference.max_results

    def test_env_does_not_load_sub_configs(self) -> None:
        """Environment variables don't support nested config, so sub-configs stay default."""
        import os
        env_copy = os.environ.copy()
        try:
            os.environ["CSCODE_PROVIDER"] = "azure"
            os.environ["CSCODE_EXPERIMENTAL"] = '{"tools_v2": true}'  # string, not parsed
            env_config = Config.from_env()
            assert env_config is not None
            assert env_config.provider == "azure"
            # experimental should remain default (None) because env values are strings top-level only
            assert env_config.experimental is None
        finally:
            os.environ.clear()
            os.environ.update(env_copy)
