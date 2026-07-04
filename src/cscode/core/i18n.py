from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

LANG_EN = "en"
LANG_ZH = "zh"

SUPPORTED_LANGUAGES = {LANG_EN, LANG_ZH}


TRANSLATIONS: dict[str, dict[str, str]] = {
    LANG_EN: {
        # General
        "app.name": "CScode",
        "app.description": "AI-powered coding assistant",
        "app.version": "Version {version}",
        # Errors
        "error.not_found": "Not found",
        "error.server_error": "Internal server error",
        "error.invalid_request": "Invalid request",
        "error.unauthorized": "Unauthorized",
        "error.forbidden": "Forbidden",
        "error.timeout": "Request timed out",
        "error.invalid_config": "Invalid configuration",
        "error.connection_failed": "Connection failed",
        # Session
        "session.created": "Session created",
        "session.deleted": "Session deleted",
        "session.not_found": "Session not found",
        "session.exported": "Session exported",
        "session.imported": "Session imported",
        # Tools
        "tool.executed": "Tool executed",
        "tool.not_found": "Tool not found",
        "tool.timeout": "Tool execution timed out",
        # MCP
        "mcp.connected": "MCP server connected",
        "mcp.disconnected": "MCP server disconnected",
        "mcp.error": "MCP server error",
        "mcp.oauth_required": "OAuth authentication required",
        # Config
        "config.saved": "Configuration saved",
        "config.loaded": "Configuration loaded",
        "config.invalid": "Invalid configuration value",
        # Sharing
        "share.created": "Share link created",
        "share.deleted": "Share link deleted",
        "share.expired": "Share link has expired",
        # Job
        "job.enqueued": "Job enqueued",
        "job.completed": "Job completed",
        "job.failed": "Job failed",
        "job.cancelled": "Job cancelled",
    },
    LANG_ZH: {
        # General
        "app.name": "CScode",
        "app.description": "AI 编程助手",
        "app.version": "版本 {version}",
        # Errors
        "error.not_found": "未找到",
        "error.server_error": "服务器内部错误",
        "error.invalid_request": "无效的请求",
        "error.unauthorized": "未授权",
        "error.forbidden": "禁止访问",
        "error.timeout": "请求超时",
        "error.invalid_config": "无效的配置",
        "error.connection_failed": "连接失败",
        # Session
        "session.created": "会话已创建",
        "session.deleted": "会话已删除",
        "session.not_found": "未找到会话",
        "session.exported": "会话已导出",
        "session.imported": "会话已导入",
        # Tools
        "tool.executed": "工具已执行",
        "tool.not_found": "未找到工具",
        "tool.timeout": "工具执行超时",
        # MCP
        "mcp.connected": "MCP 服务器已连接",
        "mcp.disconnected": "MCP 服务器已断开",
        "mcp.error": "MCP 服务器错误",
        "mcp.oauth_required": "需要 OAuth 认证",
        # Config
        "config.saved": "配置已保存",
        "config.loaded": "配置已加载",
        "config.invalid": "无效的配置值",
        # Sharing
        "share.created": "分享链接已创建",
        "share.deleted": "分享链接已删除",
        "share.expired": "分享链接已过期",
        # Job
        "job.enqueued": "任务已加入队列",
        "job.completed": "任务已完成",
        "job.failed": "任务失败",
        "job.cancelled": "任务已取消",
    },
}


@dataclass
class I18n:
    """Internationalization helper.

    Usage:
        i18n = I18n("zh")
        msg = i18n.t("error.not_found")  # "未找到"

    Falls back to English if key is missing in the target language.
    Returns the key itself if not found in any language.
    """

    locale: str = LANG_EN
    _translations: dict[str, str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.locale = self._normalize_locale(self.locale)

    @staticmethod
    def _normalize_locale(locale: str) -> str:
        locale = locale.lower().replace("-", "_")
        if locale.startswith("zh"):
            return LANG_ZH
        return LANG_EN

    @staticmethod
    def detect_locale() -> str:
        """Detect system locale from environment."""
        for var in ("LANG", "LC_ALL", "LC_MESSAGES"):
            val = os.environ.get(var, "")
            if val.startswith("zh"):
                return LANG_ZH
        return LANG_EN

    @property
    def translations(self) -> dict[str, str]:
        return self._get_translations(self.locale)

    def _get_translations(self, locale: str) -> dict[str, str]:
        return TRANSLATIONS.get(locale, TRANSLATIONS[LANG_EN])

    def t(self, key: str, default: str | None = None, **kwargs: Any) -> str:
        """Translate a key to the current locale.

        Args:
            key: Translation key (dot-separated, e.g. "error.not_found")
            default: Fallback text if key not found
            **kwargs: Format arguments for string interpolation

        Returns:
            Translated string
        """
        msg = TRANSLATIONS.get(self.locale, {}).get(key)
        if msg is None:
            msg = TRANSLATIONS[LANG_EN].get(key)
        if msg is None:
            msg = default or key
        if kwargs:
            try:
                msg = msg.format(**kwargs)
            except KeyError:
                pass
        return msg

    def set_locale(self, locale: str) -> None:
        self.locale = self._normalize_locale(locale)

    @property
    def is_chinese(self) -> bool:
        return self.locale == LANG_ZH


# Global singleton for convenience
_default = I18n()


def t(key: str, default: str | None = None, **kwargs: Any) -> str:
    """Convenience function using the default i18n instance."""
    return _default.t(key, default=default, **kwargs)


def set_locale(locale: str) -> None:
    """Set locale on the default i18n instance."""
    _default.set_locale(locale)


def get_i18n() -> I18n:
    """Get the default i18n instance."""
    return _default
