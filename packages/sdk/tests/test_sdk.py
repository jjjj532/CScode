from __future__ import annotations

import pytest
from cscode_sdk import create_cscode, CScodeClient


class TestCreateCScode:
    def test_create_default(self) -> None:
        app = create_cscode()
        assert app is not None
        assert hasattr(app, "version")

    def test_create_with_config(self) -> None:
        app = create_cscode({"provider": "openai", "model": "gpt-4o"})
        assert app is not None

    def test_create_version(self) -> None:
        app = create_cscode()
        assert app.version == "0.2.10"


class TestCScodeClient:
    def test_create_client(self) -> None:
        client = CScodeClient(base_url="http://localhost:8000", api_key="test-key")
        assert client.base_url == "http://localhost:8000"
        assert client.api_key == "test-key"
        assert client.headers["Authorization"] == "Bearer test-key"
