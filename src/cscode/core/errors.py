from __future__ import annotations


class CScodeError(Exception):
    """Base exception for all CScode errors."""


class ConfigError(CScodeError):
    """Configuration related errors."""


class ProviderError(CScodeError):
    """LLM provider errors."""


class ToolError(CScodeError):
    """Tool execution errors."""


class SessionError(CScodeError):
    """Session management errors."""


class PermissionDenied(CScodeError):
    """User denied a permission request."""
