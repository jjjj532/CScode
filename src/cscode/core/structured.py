from __future__ import annotations

import json
import re
from typing import Any, cast

from cscode.utils.logging import get_logger

logger = get_logger(__name__)

JSON_PATTERN = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)
INLINE_JSON = re.compile(r"\{[^{}]*\}")


def extract_json_from_text(text: str) -> dict[str, Any] | list[Any] | None:
    """Extract JSON from text, trying code blocks first, then inline."""
    for match in JSON_PATTERN.finditer(text):
        try:
            data = json.loads(match.group(1).strip())
            return cast("dict[str, Any] | list[Any]", data)
        except json.JSONDecodeError:
            continue

    for match in INLINE_JSON.finditer(text):
        try:
            data = json.loads(match.group())
            return cast("dict[str, Any] | list[Any]", data)
        except json.JSONDecodeError:
            continue

    try:
        data = json.loads(text.strip())
        return cast("dict[str, Any] | list[Any]", data)
    except json.JSONDecodeError:
        return None


def _validate_type(value: Any, expected_type: str, path: str) -> list[str]:
    """Validate a single value against a JSON Schema type."""
    errors: list[str] = []
    type_map: dict[str, Any] = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
        "null": type(None),
    }

    py_type = type_map.get(expected_type)
    if py_type and not isinstance(value, py_type):
        errors.append(f"{path}: expected {expected_type}, got {type(value).__name__}")
    return errors


def _validate_value(
    value: Any, schema: dict[str, Any], path: str = "$"
) -> list[str]:
    """Recursively validate a value against a JSON Schema."""
    errors: list[str] = []

    if not schema:
        return errors

    expected_type = schema.get("type")
    if expected_type:
        errors.extend(_validate_type(value, expected_type, path))

    enum_values = schema.get("enum")
    if enum_values is not None and value not in enum_values:
        errors.append(f"{path}: expected one of {enum_values}")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        for prop_name in required:
            if prop_name not in value:
                errors.append(f"{path}.{prop_name}: missing required field")

        for prop_name, prop_schema in properties.items():
            if prop_name in value:
                prop_path = f"{path}.{prop_name}"
                errors.extend(
                    _validate_value(value[prop_name], prop_schema, prop_path)
                )

    if isinstance(value, list):
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(value):
                errors.extend(
                    _validate_value(item, items_schema, f"{path}[{i}]")
                )

    return errors


def validate_against_schema(
    data: Any, schema: dict[str, Any]
) -> tuple[bool, str]:
    """Validate data against a JSON Schema. Returns (valid, error_message)."""
    if not schema:
        return True, ""

    if not isinstance(data, (dict, list)):
        return False, f"Expected object or array, got {type(data).__name__}"

    errors = _validate_value(data, schema)
    if errors:
        return False, "; ".join(errors)
    return True, ""


class StructuredOutputHandler:
    """Handles structured output validation and auto-retry.

    Usage:
        handler = StructuredOutputHandler(max_retries=3)
        result = handler.validate(response_text, schema)
        if result is not None:
            # Use result
        else:
            # All retries exhausted
    """

    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries

    def validate(
        self, text: str, schema: dict[str, Any]
    ) -> dict[str, Any] | list[Any] | None:
        """Validate text against schema. Returns parsed JSON or None."""
        data = extract_json_from_text(text)
        if data is None:
            logger.warning("No JSON found in response")
            return None

        valid, errors = validate_against_schema(data, schema)
        if not valid:
            logger.warning("Schema validation failed: %s", errors)
            return None

        return data
