from __future__ import annotations

import pytest
from cscode.auth.github import GitHubOAuth


class TestGitHubOAuth:
    def test_create_provider(self) -> None:
        oauth = GitHubOAuth(client_id="test-id", client_secret="test-secret")
        assert oauth.client_id == "test-id"
        assert oauth.client_secret == "test-secret"

    def test_authorize_url(self) -> None:
        oauth = GitHubOAuth(client_id="test-id", client_secret="test-secret")
        url = oauth.get_authorize_url(state="abc123")
        assert "github.com/login/oauth/authorize" in url
        assert "client_id=test-id" in url
        assert "state=abc123" in url

    def test_default_scopes(self) -> None:
        oauth = GitHubOAuth(client_id="test-id", client_secret="test-secret")
        url = oauth.get_authorize_url(state="xyz")
        assert "scope=repo%2Cuser" in url
