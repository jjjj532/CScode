from __future__ import annotations

import pytest
from cscode.auth.openai_oauth import OpenAIOAuth


class TestOpenAIOAuth:
    def test_create_provider(self) -> None:
        oauth = OpenAIOAuth(client_id="test-id", client_secret="test-secret")
        assert oauth.client_id == "test-id"

    def test_authorize_url(self) -> None:
        oauth = OpenAIOAuth(client_id="test-id", client_secret="test-secret")
        url = oauth.get_authorize_url(state="abc")
        assert "authorize.openai.com" in url
        assert "client_id=test-id" in url
