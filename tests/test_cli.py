"""Tests for cli.py"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gitlab_issue_mcp.cli import cli


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def _mock_config():
    """Return a minimal Config-like object."""
    from gitlab_issue_mcp.config import Config

    return Config(
        gitlab_url="https://gitlab.example.com",
        gitlab_api_key="glpat-test",
        llm_base_url="http://localhost:4000",
        llm_model="gpt-4o",
    )


# ---------------------------------------------------------------------------
# Top-level help
# ---------------------------------------------------------------------------


def test_cli_help(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.output
    assert "check-connection" in result.output


# ---------------------------------------------------------------------------
# check-connection command
# ---------------------------------------------------------------------------


def test_check_connection_success(runner: CliRunner, _mock_config) -> None:
    fake_user = {"username": "alice", "name": "Alice Smith"}

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=_mock_config),
        patch(
            "gitlab_issue_mcp.cli.GitLabClient",
        ) as MockClient,
    ):
        instance = MockClient.return_value
        instance.get_current_user.return_value = fake_user

        result = runner.invoke(cli, ["check-connection"])

    assert result.exit_code == 0
    assert "Successfully connected" in result.output
    assert "alice" in result.output
    assert "Alice Smith" in result.output


def test_check_connection_config_error(runner: CliRunner) -> None:
    with patch(
        "gitlab_issue_mcp.cli.load_config",
        side_effect=FileNotFoundError("No config found"),
    ):
        result = runner.invoke(cli, ["check-connection"])

    assert result.exit_code == 1
    assert "Error loading config" in result.output


def test_check_connection_auth_error(runner: CliRunner, _mock_config) -> None:
    from gitlab.exceptions import GitlabAuthenticationError

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=_mock_config),
        patch(
            "gitlab_issue_mcp.cli.GitLabClient",
        ) as MockClient,
    ):
        instance = MockClient.return_value
        instance.get_current_user.side_effect = GitlabAuthenticationError(
            "401 Unauthorized"
        )

        result = runner.invoke(cli, ["check-connection"])

    assert result.exit_code == 1
    assert "Connection failed" in result.output


def test_check_connection_with_config_flag(runner: CliRunner, _mock_config) -> None:
    """--config flag is forwarded to load_config."""
    fake_user = {"username": "bob", "name": "Bob"}

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=_mock_config) as mock_load,
        patch("gitlab_issue_mcp.cli.GitLabClient") as MockClient,
    ):
        instance = MockClient.return_value
        instance.get_current_user.return_value = fake_user

        result = runner.invoke(cli, ["--config", "/tmp/my_config.yaml", "check-connection"])

    assert result.exit_code == 0
    mock_load.assert_called_once_with("/tmp/my_config.yaml")


# ---------------------------------------------------------------------------
# serve command
# ---------------------------------------------------------------------------


def test_serve_config_error(runner: CliRunner) -> None:
    with patch(
        "gitlab_issue_mcp.cli.load_config",
        side_effect=ValueError("Missing required keys"),
    ):
        result = runner.invoke(cli, ["serve"])

    assert result.exit_code == 1
    assert "Error" in result.output


def test_serve_invalid_transport(runner: CliRunner, _mock_config) -> None:
    _mock_config.mcp_transport = "invalid"

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=_mock_config),
        patch("gitlab_issue_mcp.cli.create_server", return_value=MagicMock()),
    ):
        result = runner.invoke(cli, ["serve"])

    assert result.exit_code == 1
    assert "Invalid mcp_transport" in result.output


def test_serve_runs_mcp(runner: CliRunner, _mock_config) -> None:
    mock_mcp = MagicMock()

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=_mock_config),
        patch("gitlab_issue_mcp.cli.create_server", return_value=mock_mcp),
    ):
        result = runner.invoke(cli, ["serve"])

    mock_mcp.run.assert_called_once_with(transport="stdio")
    assert result.exit_code == 0
