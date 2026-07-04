"""Tests for P0-4: Config Attachments — AttachmentConfig + ConfigV2 integration.

Tests cover:
- AttachmentConfig defaults and validation
- Serialisation roundtrip via to_dict/from_dict
- ConfigV2 merge with attachment config
- Attachment model and basic validation
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cscode.core.permission_v2 import Rule, RuleEffect, Ruleset


# ─── AttachmentConfig ────────────────────────────────────────────────


class TestAttachmentConfigDefaults:
    """AttachmentConfig default values."""

    def test_defaults(self) -> None:
        from cscode.core.config_v2 import AttachmentConfig

        cfg = AttachmentConfig()
        assert cfg.max_size == 10 * 1024 * 1024  # 10 MB
        assert ".py" in cfg.allowed_extensions
        assert ".ts" in cfg.allowed_extensions
        assert ".md" in cfg.allowed_extensions
        assert cfg.max_count == 10
        assert cfg.allow_all is False
        assert cfg.base_dir is None

    def test_custom_values(self) -> None:
        from cscode.core.config_v2 import AttachmentConfig

        cfg = AttachmentConfig(
            max_size=1024,
            allowed_extensions=(".txt", ".md"),
            max_count=3,
            allow_all=False,
            base_dir="/tmp/attachments",
        )
        assert cfg.max_size == 1024
        assert cfg.allowed_extensions == (".txt", ".md")
        assert cfg.max_count == 3
        assert cfg.base_dir == "/tmp/attachments"


class TestAttachmentConfigValidation:
    """AttachmentConfig validation rules."""

    def test_validate_extension_allowed(self) -> None:
        from cscode.core.config_v2 import AttachmentConfig

        cfg = AttachmentConfig(allowed_extensions=(".py", ".ts"))
        assert cfg.is_extension_allowed("main.py") is True
        assert cfg.is_extension_allowed("file.ts") is True
        assert cfg.is_extension_allowed("file.md") is False
        assert cfg.is_extension_allowed("file") is False

    def test_allow_all_overrides_extension_check(self) -> None:
        from cscode.core.config_v2 import AttachmentConfig

        cfg = AttachmentConfig(allow_all=True, allowed_extensions=(".py",))
        assert cfg.is_extension_allowed("image.png") is True
        assert cfg.is_extension_allowed("file.bin") is True

    def test_validate_size(self) -> None:
        from cscode.core.config_v2 import AttachmentConfig

        cfg = AttachmentConfig(max_size=1000)
        assert cfg.is_size_allowed(500) is True
        assert cfg.is_size_allowed(1000) is True
        assert cfg.is_size_allowed(1001) is False

    def test_validate_max_count(self) -> None:
        from cscode.core.config_v2 import AttachmentConfig

        cfg = AttachmentConfig(max_count=3)
        assert cfg.is_count_allowed(3) is True
        assert cfg.is_count_allowed(4) is False


# ─── ConfigV2 Integration ────────────────────────────────────────────


class TestAttachmentConfigV2Integration:
    """AttachmentConfig integrated into ConfigV2."""

    def test_default_config_v2_has_no_attachment(self) -> None:
        from cscode.core.config_v2 import ConfigV2

        cfg = ConfigV2()
        assert cfg.attachment is None

    def test_config_v2_with_attachment(self) -> None:
        from cscode.core.config_v2 import AttachmentConfig, ConfigV2

        cfg = ConfigV2(attachment=AttachmentConfig(max_size=2048))
        assert cfg.attachment is not None
        assert cfg.attachment.max_size == 2048

    def test_to_dict_excludes_when_none(self) -> None:
        from cscode.core.config_v2 import ConfigV2

        cfg = ConfigV2()
        d = cfg.to_dict()
        assert "attachment" not in d

    def test_to_dict_includes_attachment(self) -> None:
        from cscode.core.config_v2 import AttachmentConfig, ConfigV2

        cfg = ConfigV2(attachment=AttachmentConfig(
            max_size=2048,
            allowed_extensions=(".py", ".ts"),
            max_count=5,
            allow_all=False,
            base_dir="/tmp/attachments",
        ))
        d = cfg.to_dict()
        assert "attachment" in d
        assert d["attachment"]["max_size"] == 2048
        assert ".py" in d["attachment"]["allowed_extensions"]
        assert d["attachment"]["max_count"] == 5
        assert d["attachment"]["allow_all"] is False
        assert d["attachment"]["base_dir"] == "/tmp/attachments"

    def test_from_dict_with_attachment(self) -> None:
        from cscode.core.config_v2 import ConfigV2

        cfg = ConfigV2.from_dict({
            "attachment": {
                "max_size": 4096,
                "allowed_extensions": [".md", ".txt"],
                "max_count": 3,
                "allow_all": True,
                "base_dir": "/data/attachments",
            },
        })
        assert cfg.attachment is not None
        assert cfg.attachment.max_size == 4096
        assert cfg.attachment.allowed_extensions == (".md", ".txt")
        assert cfg.attachment.max_count == 3
        assert cfg.attachment.allow_all is True
        assert cfg.attachment.base_dir == "/data/attachments"

    def test_from_dict_partial_attachment(self) -> None:
        from cscode.core.config_v2 import ConfigV2

        cfg = ConfigV2.from_dict({
            "attachment": {
                "max_size": 8192,
            },
        })
        assert cfg.attachment is not None
        assert cfg.attachment.max_size == 8192
        # Other fields should have defaults
        assert cfg.attachment.max_count == 10
        assert cfg.attachment.allow_all is False

    def test_merge_no_attachment(self) -> None:
        from cscode.core.config_v2 import ConfigV2

        base = ConfigV2()
        overlay = ConfigV2()
        merged = base.merge(overlay)
        assert merged.attachment is None

    def test_merge_overlay_attachment_wins(self) -> None:
        from cscode.core.config_v2 import AttachmentConfig, ConfigV2

        base = ConfigV2(attachment=AttachmentConfig(max_size=1000))
        overlay = ConfigV2(attachment=AttachmentConfig(max_size=9999))
        merged = base.merge(overlay)
        assert merged.attachment is not None
        assert merged.attachment.max_size == 9999

    def test_to_legacy_preserves_attachment(self) -> None:
        from cscode.core.config_v2 import AttachmentConfig, ConfigV2

        v2 = ConfigV2(attachment=AttachmentConfig(max_size=2048))
        legacy = v2.to_legacy()
        assert legacy is not None
        # Legacy doesn't have attachment field, but conversion should not error

    def test_roundtrip_dict(self) -> None:
        from cscode.core.config_v2 import AttachmentConfig, ConfigV2

        original = ConfigV2(attachment=AttachmentConfig(
            max_size=5000,
            allowed_extensions=(".py", ".ts", ".js"),
            max_count=5,
            allow_all=True,
            base_dir="/tmp/x",
        ))
        d = original.to_dict()
        restored = ConfigV2.from_dict(d)
        assert restored.attachment is not None
        assert restored.attachment.max_size == 5000
        assert ".py" in restored.attachment.allowed_extensions
        assert restored.attachment.max_count == 5
        assert restored.attachment.allow_all is True
        assert restored.attachment.base_dir == "/tmp/x"


# ─── Attachment Model ────────────────────────────────────────────────


class TestAttachmentBasic:
    """Attachment dataclass and basic operations."""

    def test_create_attachment(self) -> None:
        from cscode.core.attachment import Attachment

        att = Attachment(path="/tmp/test.py", name="test.py", content="print('hello')", size=15)
        assert att.path == "/tmp/test.py"
        assert att.name == "test.py"
        assert att.content == "print('hello')"
        assert att.size == 15
        # .py files get text/x-python from mimetypes
        assert att.mime_type in ("text/plain", "text/x-python")
        assert att.is_image is False

    def test_attachment_is_text(self) -> None:
        from cscode.core.attachment import Attachment

        att = Attachment(path="/tmp/file.py", name="file.py", content="x", size=1)
        assert att.is_text is True
        assert att.is_image is False

    def test_attachment_is_image(self) -> None:
        from cscode.core.attachment import Attachment

        att = Attachment(path="/tmp/image.png", name="image.png", content="", size=0, is_image=True)
        assert att.is_image is True
        assert att.is_text is False

    def test_attachment_mime_inferred(self) -> None:
        from cscode.core.attachment import Attachment

        att = Attachment(path="/tmp/style.css", name="style.css", content="body {}", size=7)
        assert att.mime_type == "text/css"

    def test_unknown_extension_mime(self) -> None:
        from cscode.core.attachment import Attachment

        att = Attachment(path="/tmp/file.xyz", name="file.xyz", content="data", size=4)
        # mimetypes may return application/octet-stream or chemical/x-xyz
        assert att.mime_type != ""
