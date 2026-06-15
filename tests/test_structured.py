from __future__ import annotations

import pytest
from cscode.core.structured import (
    validate_against_schema,
    StructuredOutputHandler,
    extract_json_from_text,
)


class TestExtractJson:
    def test_extract_from_code_block(self) -> None:
        text = "Here is the result:\n```json\n{\"key\": \"value\"}\n```"
        result = extract_json_from_text(text)
        assert result == {"key": "value"}

    def test_extract_from_plain_json(self) -> None:
        text = '{"name": "test", "count": 42}'
        result = extract_json_from_text(text)
        assert result == {"name": "test", "count": 42}

    def test_extract_from_text_with_json(self) -> None:
        text = "The result is: {\"id\": 1, \"status\": \"ok\"} and that's it."
        result = extract_json_from_text(text)
        assert result == {"id": 1, "status": "ok"}

    def test_no_json_returns_none(self) -> None:
        text = "There is no JSON here at all."
        result = extract_json_from_text(text)
        assert result is None


class TestValidateAgainstSchema:
    def test_valid_data_passes(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        }
        data = {"name": "Alice", "age": 30}
        valid, errors = validate_against_schema(data, schema)
        assert valid
        assert errors == ""

    def test_missing_required_field(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        }
        data = {"age": 30}
        valid, errors = validate_against_schema(data, schema)
        assert not valid
        assert "name" in errors.lower() or "required" in errors.lower()

    def test_wrong_type(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
            },
        }
        data = {"count": "not_a_number"}
        valid, errors = validate_against_schema(data, schema)
        assert not valid

    def test_invalid_data_not_dict(self) -> None:
        schema = {"type": "object"}
        valid, errors = validate_against_schema("not_a_dict", schema)
        assert not valid

    def test_empty_schema(self) -> None:
        """Empty schema should accept any data."""
        schema = {}
        valid, errors = validate_against_schema({"anything": "goes"}, schema)
        assert valid

    def test_array_type(self) -> None:
        schema = {
            "type": "array",
            "items": {"type": "string"},
        }
        valid, errors = validate_against_schema(["a", "b", "c"], schema)
        assert valid

    def test_array_with_invalid_items(self) -> None:
        schema = {
            "type": "array",
            "items": {"type": "integer"},
        }
        valid, errors = validate_against_schema(["a", "b"], schema)
        assert not valid


class TestStructuredOutputHandler:
    def test_init_defaults(self) -> None:
        handler = StructuredOutputHandler()
        assert handler.max_retries == 3

    def test_valid_response_passes_through(self) -> None:
        handler = StructuredOutputHandler()
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
        response = handler.validate('{"ok": true}', schema)
        assert response is not None
