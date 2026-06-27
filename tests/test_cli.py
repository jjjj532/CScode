from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cscode import __version__
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
        assert __version__ in result.output

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
        assert "browser" in result.output

    def test_desktop_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["desktop", "--help"])
        assert result.exit_code == 0
        assert "desktop" in result.output
