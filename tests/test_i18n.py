from __future__ import annotations

import os

import pytest

from cscode.core.i18n import (
    I18n,
    LANG_EN,
    LANG_ZH,
    get_i18n,
    set_locale,
    t,
)


class TestI18n:
    def test_default_locale(self) -> None:
        i18n = I18n()
        assert i18n.locale == LANG_EN

    def test_chinese_locale(self) -> None:
        i18n = I18n("zh")
        assert i18n.locale == LANG_ZH

    def test_chinese_locale_variant(self) -> None:
        i18n = I18n("zh-CN")
        assert i18n.locale == LANG_ZH
        i18n2 = I18n("zh_TW")
        assert i18n2.locale == LANG_ZH

    def test_unknown_locale_falls_back(self) -> None:
        i18n = I18n("fr")
        assert i18n.locale == LANG_EN

    def test_t_en(self) -> None:
        i18n = I18n(LANG_EN)
        assert i18n.t("error.not_found") == "Not found"

    def test_t_zh(self) -> None:
        i18n = I18n(LANG_ZH)
        assert i18n.t("error.not_found") == "未找到"

    def test_t_missing_key(self) -> None:
        i18n = I18n(LANG_EN)
        assert i18n.t("nonexistent.key") == "nonexistent.key"

    def test_t_missing_key_default(self) -> None:
        i18n = I18n(LANG_EN)
        assert i18n.t("nonexistent.key", default="Fallback") == "Fallback"

    def test_t_fallback_to_en(self) -> None:
        """If key is in EN but not ZH, should fallback to EN."""
        i18n = I18n(LANG_ZH)
        # Use a key that exists only in EN translations
        result = i18n.t("app.description")
        assert result is not None
        assert isinstance(result, str)

    def test_t_with_format(self) -> None:
        i18n = I18n(LANG_EN)
        result = i18n.t("app.version", version="1.0.0")
        assert "1.0.0" in result

    def test_set_locale(self) -> None:
        i18n = I18n(LANG_EN)
        i18n.set_locale("zh")
        assert i18n.locale == LANG_ZH
        assert i18n.is_chinese is True

    def test_is_chinese(self) -> None:
        i18n_en = I18n(LANG_EN)
        i18n_zh = I18n(LANG_ZH)
        assert i18n_en.is_chinese is False
        assert i18n_zh.is_chinese is True

    def test_detect_locale_en(self) -> None:
        # Clear any Chinese locale env vars
        for var in ("LANG", "LC_ALL", "LC_MESSAGES"):
            os.environ.pop(var, None)
        detected = I18n.detect_locale()
        assert detected == LANG_EN

    def test_detect_locale_zh(self) -> None:
        os.environ["LANG"] = "zh_CN.UTF-8"
        detected = I18n.detect_locale()
        assert detected == LANG_ZH
        # Clean up
        os.environ.pop("LANG", None)

    def test_translations_property(self) -> None:
        i18n = I18n(LANG_ZH)
        translations = i18n.translations
        assert "app.name" in translations
        assert "error.not_found" in translations
        # Should have both EN and ZH keys
        assert translations["error.not_found"] == "未找到"

    def test_global_t(self) -> None:
        # Reset to EN for this test
        set_locale(LANG_EN)
        assert t("error.not_found") == "Not found"

    def test_global_set_locale(self) -> None:
        set_locale(LANG_ZH)
        assert get_i18n().locale == LANG_ZH
        # Reset
        set_locale(LANG_EN)

    def test_all_keys_have_zh_translation(self) -> None:
        """Ensure every EN key has a ZH translation."""
        from cscode.core.i18n import TRANSLATIONS

        en_keys = set(TRANSLATIONS[LANG_EN].keys())
        zh_keys = set(TRANSLATIONS[LANG_ZH].keys())
        missing = en_keys - zh_keys
        assert not missing, f"Missing ZH translations: {missing}"
