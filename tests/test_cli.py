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
def mock_config():
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


def test_check_connection_success(runner: CliRunner, mock_config) -> None:
    fake_user = {"username": "alice", "name": "Alice Smith"}

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=mock_config),
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


def test_check_connection_auth_error(runner: CliRunner, mock_config) -> None:
    from gitlab.exceptions import GitlabAuthenticationError

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=mock_config),
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
    assert "Authentication failed" in result.output


def test_check_connection_with_config_flag(runner: CliRunner, mock_config) -> None:
    """--config flag is forwarded to load_config."""
    fake_user = {"username": "bob", "name": "Bob"}

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=mock_config) as mock_load,
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


def test_serve_invalid_transport(runner: CliRunner, mock_config) -> None:
    mock_config.mcp_transport = "invalid"

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=mock_config),
        patch("gitlab_issue_mcp.cli.create_server", return_value=MagicMock()),
    ):
        result = runner.invoke(cli, ["serve"])

    assert result.exit_code == 1
    assert "Invalid mcp_transport" in result.output


def test_serve_runs_mcp(runner: CliRunner, mock_config) -> None:
    mock_mcp = MagicMock()

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=mock_config),
        patch("gitlab_issue_mcp.cli.create_server", return_value=mock_mcp),
    ):
        result = runner.invoke(cli, ["serve"])

    mock_mcp.run.assert_called_once_with(transport="stdio")
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# list-tools / call-tool commands
# ---------------------------------------------------------------------------


def _fake_tool(name: str, description: str = "", input_schema: dict | None = None):
    """Return a stand-in for ``mcp.types.Tool`` with the attributes used by CLI."""
    tool = MagicMock()
    tool.name = name
    tool.description = description
    tool.inputSchema = input_schema or {}
    return tool


def _make_async_mcp(tools, call_tool_return=None, call_tool_side_effect=None):
    """Build a MagicMock FastMCP whose async methods return canned values."""
    mcp = MagicMock()

    async def _list_tools():
        return tools

    async def _call_tool(name, arguments):
        if call_tool_side_effect is not None:
            raise call_tool_side_effect
        return call_tool_return

    mcp.list_tools = _list_tools
    mcp.call_tool = _call_tool
    return mcp


def test_list_tools_human_readable(runner: CliRunner, mock_config) -> None:
    tools = [
        _fake_tool(
            "list_issues",
            "List GitLab issues with optional filtering.",
            {
                "properties": {
                    "state": {"type": "string"},
                    "project_id": {"type": "integer"},
                },
                "required": [],
            },
        ),
        _fake_tool("get_issue", "Get a single issue."),
    ]
    mcp = _make_async_mcp(tools)

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=mock_config),
        patch("gitlab_issue_mcp.cli.create_server", return_value=mcp),
    ):
        result = runner.invoke(cli, ["list-tools"])

    assert result.exit_code == 0, result.output
    assert "list_issues" in result.output
    assert "get_issue" in result.output
    assert "state" in result.output
    assert "project_id" in result.output


def test_list_tools_json(runner: CliRunner, mock_config) -> None:
    import json as _json

    tools = [
        _fake_tool(
            "list_issues",
            "List GitLab issues.",
            {"properties": {"state": {"type": "string"}}, "required": []},
        ),
    ]
    mcp = _make_async_mcp(tools)

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=mock_config),
        patch("gitlab_issue_mcp.cli.create_server", return_value=mcp),
    ):
        result = runner.invoke(cli, ["list-tools", "--json"])

    assert result.exit_code == 0, result.output
    payload = _json.loads(result.output)
    assert payload[0]["name"] == "list_issues"
    assert payload[0]["inputSchema"]["properties"]["state"]["type"] == "string"


def test_call_tool_with_arg_options(runner: CliRunner, mock_config) -> None:
    from mcp.types import TextContent

    tools = [_fake_tool("list_issues", "List issues.")]
    captured: dict = {}

    async def _call_tool(name, arguments):
        captured["name"] = name
        captured["arguments"] = arguments
        return ([TextContent(type="text", text='[{"id": 1}]')], {"result": "ok"})

    mcp = _make_async_mcp(tools)
    mcp.call_tool = _call_tool

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=mock_config),
        patch("gitlab_issue_mcp.cli.create_server", return_value=mcp),
    ):
        result = runner.invoke(
            cli,
            [
                "call-tool",
                "list_issues",
                "--arg",
                "state=opened",
                "--arg",
                "project_id=42",
                "--arg",
                "labels=bug,urgent",
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured["name"] == "list_issues"
    # state -> string (not valid JSON), project_id -> int via JSON parsing,
    # labels -> string (commas are not valid JSON).
    assert captured["arguments"] == {
        "state": "opened",
        "project_id": 42,
        "labels": "bug,urgent",
    }
    assert '[{"id": 1}]' in result.output
    assert "Result of list_issues" in result.output


def test_call_tool_with_json_option(runner: CliRunner, mock_config) -> None:
    from mcp.types import TextContent

    tools = [_fake_tool("list_issues", "List issues.")]
    captured: dict = {}

    async def _call_tool(name, arguments):
        captured["arguments"] = arguments
        return ([TextContent(type="text", text="ok")], {})

    mcp = _make_async_mcp(tools)
    mcp.call_tool = _call_tool

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=mock_config),
        patch("gitlab_issue_mcp.cli.create_server", return_value=mcp),
    ):
        result = runner.invoke(
            cli,
            [
                "call-tool",
                "list_issues",
                "--json",
                '{"state": "closed", "project_id": 7}',
                "--raw",
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured["arguments"] == {"state": "closed", "project_id": 7}
    # --raw suppresses the header line.
    assert "Result of" not in result.output
    assert "ok" in result.output


def test_call_tool_with_json_stdin(runner: CliRunner, mock_config) -> None:
    """--json - reads the JSON payload from stdin."""
    from mcp.types import TextContent

    tools = [_fake_tool("list_issues", "List issues.")]
    captured: dict = {}

    async def _call_tool(name, arguments):
        captured["arguments"] = arguments
        return ([TextContent(type="text", text="ok")], {})

    mcp = _make_async_mcp(tools)
    mcp.call_tool = _call_tool

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=mock_config),
        patch("gitlab_issue_mcp.cli.create_server", return_value=mcp),
    ):
        result = runner.invoke(
            cli,
            ["call-tool", "list_issues", "--json", "-"],
            input='{"state": "opened", "project_id": 99}',
        )

    assert result.exit_code == 0, result.output
    assert captured["arguments"] == {"state": "opened", "project_id": 99}
    assert "ok" in result.output


def test_call_tool_unknown_tool(runner: CliRunner, mock_config) -> None:
    tools = [_fake_tool("list_issues", "List issues.")]
    mcp = _make_async_mcp(tools)

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=mock_config),
        patch("gitlab_issue_mcp.cli.create_server", return_value=mcp),
    ):
        result = runner.invoke(cli, ["call-tool", "does_not_exist"])

    assert result.exit_code == 2
    assert "unknown tool" in result.output
    assert "list_issues" in result.output


def test_call_tool_invalid_arg_format(runner: CliRunner, mock_config) -> None:
    tools = [_fake_tool("list_issues", "List issues.")]
    mcp = _make_async_mcp(tools)

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=mock_config),
        patch("gitlab_issue_mcp.cli.create_server", return_value=mcp),
    ):
        result = runner.invoke(
            cli, ["call-tool", "list_issues", "--arg", "no_equals_sign"]
        )

    assert result.exit_code == 2
    assert "KEY=VALUE" in result.output


def test_call_tool_arg_and_json_mutually_exclusive(
    runner: CliRunner, mock_config
) -> None:
    with patch("gitlab_issue_mcp.cli.load_config", return_value=mock_config):
        result = runner.invoke(
            cli,
            [
                "call-tool",
                "list_issues",
                "--arg",
                "state=opened",
                "--json",
                "{}",
            ],
        )

    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


def test_call_tool_invalid_json(runner: CliRunner, mock_config) -> None:
    with patch("gitlab_issue_mcp.cli.load_config", return_value=mock_config):
        result = runner.invoke(
            cli, ["call-tool", "list_issues", "--json", "{not json}"]
        )

    assert result.exit_code == 2
    assert "not valid JSON" in result.output


def test_call_tool_json_must_be_object(runner: CliRunner, mock_config) -> None:
    with patch("gitlab_issue_mcp.cli.load_config", return_value=mock_config):
        result = runner.invoke(
            cli, ["call-tool", "list_issues", "--json", "[1, 2]"]
        )

    assert result.exit_code == 2
    assert "must be a JSON object" in result.output


def test_call_tool_propagates_runtime_error(runner: CliRunner, mock_config) -> None:
    tools = [_fake_tool("list_issues", "List issues.")]
    mcp = _make_async_mcp(tools, call_tool_side_effect=RuntimeError("boom"))

    with (
        patch("gitlab_issue_mcp.cli.load_config", return_value=mock_config),
        patch("gitlab_issue_mcp.cli.create_server", return_value=mcp),
    ):
        result = runner.invoke(cli, ["call-tool", "list_issues"])

    assert result.exit_code == 1
    assert "Error invoking tool" in result.output
    assert "boom" in result.output
