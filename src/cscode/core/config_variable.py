from __future__ import annotations

import os
import re
from typing import Any

__all__ = ["resolve_variables", "resolve_config"]

_VAR_PATTERN = re.compile(r"\$\{env\.([^}:]+)(?::-([^}]*))?\}")


def resolve_variables(value: str) -> str:
    """Resolve ${env.VAR} and ${env.VAR:-default} in a string.

    - ``${env.HOME}`` → ``os.environ["HOME"]`` (``""`` if unset)
    - ``${env.MISSING:-fallback}`` → ``"fallback"``
    - Plain strings are returned unchanged.

    Only single-level env var references are supported (no nesting).
    """
    if not value or "${" not in value:
        return value

    def _replace(m: re.Match[str]) -> str:
        var = m.group(1)
        default = m.group(2)
        if default is not None:
            val = os.environ.get(var)
            return val if val is not None else default
        val = os.environ.get(var)
        return val if val is not None else ""

    return _VAR_PATTERN.sub(_replace, value)


def resolve_config(config: dict[str, Any]) -> dict[str, Any]:
    """Recursively resolve variables in a config dictionary.

    All string values are passed through :func:`resolve_variables`.
    Nested dict values are resolved recursively. Lists and other types
    are returned unchanged.
    """
    resolved: dict[str, Any] = {}
    for key, val in config.items():
        if isinstance(val, str):
            resolved[key] = resolve_variables(val)
        elif isinstance(val, dict):
            resolved[key] = resolve_config(val)
        else:
            resolved[key] = val
    return resolved
