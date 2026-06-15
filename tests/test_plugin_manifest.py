from __future__ import annotations

import json
from pathlib import Path

import pytest

from cscode.plugins.manifest import PluginManifest, load_manifest


class TestPluginManifest:
    def test_create_manifest(self) -> None:
        m = PluginManifest(
            name="test-plugin",
            version="1.0.0",
            description="A test plugin",
        )
        assert m.name == "test-plugin"
        assert m.version == "1.0.0"

    def test_load_manifest_valid(self, tmp_path: Path) -> None:
        data = {
            "name": "my-plugin",
            "version": "0.1.0",
            "description": "My plugin",
            "author": "test",
            "hooks": ["tool.execute.before", "session.created"],
        }
        manifest_file = tmp_path / "plugin.json"
        manifest_file.write_text(json.dumps(data))

        m = load_manifest(str(manifest_file))
        assert m is not None
        assert m.name == "my-plugin"
        assert "tool.execute.before" in m.hooks

    def test_load_manifest_missing(self) -> None:
        m = load_manifest("/nonexistent/plugin.json")
        assert m is None

    def test_load_manifest_invalid_json(self, tmp_path: Path) -> None:
        manifest_file = tmp_path / "plugin.json"
        manifest_file.write_text("not json")

        m = load_manifest(str(manifest_file))
        assert m is None

    def test_load_manifest_missing_required(self, tmp_path: Path) -> None:
        manifest_file = tmp_path / "plugin.json"
        manifest_file.write_text(json.dumps({"name": "only-name"}))

        m = load_manifest(str(manifest_file))
        assert m is not None
        assert m.version == "0.0.0"
