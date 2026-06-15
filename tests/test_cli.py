from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cscode.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestCLI:
    def test_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "CScode" in result.output

    def test_version(self, runner: CliRunner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_chat_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["chat", "--help"])
        assert result.exit_code == 0
        assert "prompt" in result.output

    def test_config_no_args(self, runner: CliRunner):
        result = runner.invoke(cli, ["config"])
        assert result.exit_code == 0

    def test_review_no_args(self, runner: CliRunner):
        result = runner.invoke(cli, ["review"])
        assert result.exit_code == 0

    def test_server_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["server", "--help"])
        assert result.exit_code == 0
        assert "port" in result.output

    def test_web_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["web", "--help"])
        assert result.exit_code == 0
        assert "port" in result.output

    def test_desktop_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["desktop", "--help"])
        assert result.exit_code == 0
        assert "desktop" in result.output

    def test_session_list_command(self, runner: CliRunner):
        result = runner.invoke(cli, ["session", "list"])
        assert result.exit_code == 0
        assert "Session" in result.output or "No sessions" in result.output

    def test_session_new_command(self, runner: CliRunner):
        result = runner.invoke(cli, ["session", "new", "--name", "test-session"])
        assert result.exit_code == 0
        assert "test-session" in result.output

    def test_session_use_command(self, runner: CliRunner):
        result = runner.invoke(cli, ["session", "new", "--name", "session-to-use"])
        assert result.exit_code == 0
        session_id = result.output.split("\n")[0].replace("Created session: ", "")
        result = runner.invoke(cli, ["session", "use", session_id])
        assert result.exit_code == 0
        assert "session-to-use" in result.output

    def test_session_kill_command(self, runner: CliRunner):
        result = runner.invoke(cli, ["session", "new", "--name", "session-to-kill"])
        assert result.exit_code == 0
        session_id = result.output.split("\n")[0].replace("Created session: ", "")
        result = runner.invoke(cli, ["session", "kill", session_id])
        assert result.exit_code == 0
        assert "terminated" in result.output.lower()
