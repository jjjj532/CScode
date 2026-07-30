"""Config endpoint contracts — typed API shapes for configuration.

These types define the request/response shapes for /api/config/* endpoints.
No FastAPI dependency — pure contract definitions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConfigItem:
    """A single key-value configuration entry."""

    key: str
    """Configuration key name."""
    value: str
    """Configuration value."""


@dataclass(frozen=True, slots=True)
class ConfigResponse:
    """Response body for GET /api/config."""

    config: list[ConfigItem]
    """List of configuration entries."""


@dataclass(frozen=True, slots=True)
class ConfigUpdateRequest:
    """Request body for PUT /api/config."""

    config: list[ConfigItem]
    """Configuration entries to update."""


@dataclass(frozen=True, slots=True)
class ConfigReferenceItem:
    """A single entry in the config reference (GET /api/config/reference)."""

    key: str
    """Configuration key name."""
    type: str
    """Value type description (string, int, float, etc.)."""
    description: str
    """Human-readable description of the config key."""
    default: str
    """Default value as a string."""
