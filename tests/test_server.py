"""Tests for server.py (MCP tool functions)"""

from __future__ import annotations

import json
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
import yaml

from gitlab_issue_mcp.config import Config
from gitlab_issue_mcp.server import create_server


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config() -> Config:
    return Config(
        gitlab_url="https://gitlab.example.com",
        gitlab_api_key="glpat-test",
        llm_base_url="http://localhost:4000",
        llm_model="gpt-4o",
        llm_api_key="sk-test",
        gitlab_project_id=42,
    )


@pytest.fixture()
def sample_issues() -> List[Dict[str, Any]]:
    return [
        {
            "iid": 1,
            "title": "Issue Alpha",
            "state": "opened",
            "assignees": [{"username": "alice"}],
            "author": {"username": "bob"},
            "labels": ["bug"],
            "milestone": None,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
            "description": "Desc alpha",
            "web_url": "https://gitlab.example.com/-/issues/1",
        }
    ]


@pytest.fixture()
def mock_gitlab_client(sample_issues: List[Dict[str, Any]]) -> MagicMock:
    client = MagicMock()
    client.get_issues.return_value = sample_issues
    client.get_issue.return_value = sample_issues[0]
    client.get_user.return_value = {"username": "alice", "id": 1}
    client.get_project.return_value = {"id": 42, "name": "Test Project"}
    return client


@pytest.fixture()
def mock_qa_agent() -> MagicMock:
    agent = MagicMock()
    agent.answer_question.return_value = "Issue #1 is a bug."
    return agent


@pytest.fixture()
def server_tools(config, mock_gitlab_client, mock_qa_agent):
    """Return the FastMCP instance with patched dependencies."""
    with (
        patch("gitlab_issue_mcp.server.GitLabClient", return_value=mock_gitlab_client),
        patch("gitlab_issue_mcp.server.IssueQAAgent", return_value=mock_qa_agent),
    ):
        mcp = create_server(config)
    return mcp, mock_gitlab_client, mock_qa_agent


# ---------------------------------------------------------------------------
# Helper: call a tool by name
# ---------------------------------------------------------------------------


def _call_tool(mcp, name: str, **kwargs):
    """Find a registered tool by name and call it."""
    for tool in mcp._tool_manager._tools.values():
        if tool.name == name:
            # Tool functions are stored on the tool object
            return tool.fn(**kwargs)
    raise KeyError(f"Tool '{name}' not found in server")


# ---------------------------------------------------------------------------
# list_issues
# ---------------------------------------------------------------------------


def test_list_issues_returns_json(server_tools) -> None:
    mcp, client, _ = server_tools
    result = _call_tool(mcp, "list_issues")
    data = json.loads(result)
    assert isinstance(data, list)
    assert data[0]["iid"] == 1


def test_list_issues_passes_filters(server_tools) -> None:
    mcp, client, _ = server_tools
    _call_tool(mcp, "list_issues", state="opened", assignee_username="alice", labels="bug")
    client.get_issues.assert_called_once()
    _, kwargs = client.get_issues.call_args
    assert kwargs["state"] == "opened"
    assert kwargs["assignee_username"] == "alice"
    assert kwargs["labels"] == "bug"


def test_list_issues_uses_config_project_id(server_tools) -> None:
    mcp, client, _ = server_tools
    _call_tool(mcp, "list_issues")
    _, kwargs = client.get_issues.call_args
    assert kwargs["project_id"] == 42  # from config fixture


def test_list_issues_override_project_id(server_tools) -> None:
    mcp, client, _ = server_tools
    _call_tool(mcp, "list_issues", project_id=99)
    _, kwargs = client.get_issues.call_args
    assert kwargs["project_id"] == 99


# ---------------------------------------------------------------------------
# get_issue
# ---------------------------------------------------------------------------


def test_get_issue_returns_json(server_tools) -> None:
    mcp, client, _ = server_tools
    result = _call_tool(mcp, "get_issue", issue_iid=1)
    data = json.loads(result)
    assert data["iid"] == 1


def test_get_issue_uses_config_project_id(server_tools) -> None:
    mcp, client, _ = server_tools
    _call_tool(mcp, "get_issue", issue_iid=1)
    client.get_issue.assert_called_once_with(issue_iid=1, project_id=42)


def test_get_issue_no_project_id_returns_error(config, mock_gitlab_client, mock_qa_agent) -> None:
    config_no_project = Config(
        gitlab_url=config.gitlab_url,
        gitlab_api_key=config.gitlab_api_key,
        llm_base_url=config.llm_base_url,
        llm_model=config.llm_model,
        gitlab_project_id=None,
    )
    with (
        patch("gitlab_issue_mcp.server.GitLabClient", return_value=mock_gitlab_client),
        patch("gitlab_issue_mcp.server.IssueQAAgent", return_value=mock_qa_agent),
    ):
        mcp = create_server(config_no_project)

    result = _call_tool(mcp, "get_issue", issue_iid=1)
    data = json.loads(result)
    assert "error" in data


# ---------------------------------------------------------------------------
# get_user_issues
# ---------------------------------------------------------------------------


def test_get_user_issues(server_tools) -> None:
    mcp, client, _ = server_tools
    result = _call_tool(mcp, "get_user_issues", username="alice")
    data = json.loads(result)
    assert isinstance(data, list)
    _, kwargs = client.get_issues.call_args
    assert kwargs["assignee_username"] == "alice"


# ---------------------------------------------------------------------------
# get_user_profile
# ---------------------------------------------------------------------------


def test_get_user_profile(server_tools) -> None:
    mcp, client, _ = server_tools
    result = _call_tool(mcp, "get_user_profile", username="alice")
    data = json.loads(result)
    assert data["username"] == "alice"


# ---------------------------------------------------------------------------
# get_project_info
# ---------------------------------------------------------------------------


def test_get_project_info(server_tools) -> None:
    mcp, client, _ = server_tools
    result = _call_tool(mcp, "get_project_info")
    data = json.loads(result)
    assert data["id"] == 42


def test_get_project_info_no_project_returns_error(
    config, mock_gitlab_client, mock_qa_agent
) -> None:
    config_no_project = Config(
        gitlab_url=config.gitlab_url,
        gitlab_api_key=config.gitlab_api_key,
        llm_base_url=config.llm_base_url,
        llm_model=config.llm_model,
        gitlab_project_id=None,
    )
    with (
        patch("gitlab_issue_mcp.server.GitLabClient", return_value=mock_gitlab_client),
        patch("gitlab_issue_mcp.server.IssueQAAgent", return_value=mock_qa_agent),
    ):
        mcp = create_server(config_no_project)

    result = _call_tool(mcp, "get_project_info")
    data = json.loads(result)
    assert "error" in data


# ---------------------------------------------------------------------------
# ask_about_issues
# ---------------------------------------------------------------------------


def test_ask_about_issues_calls_agent(server_tools) -> None:
    mcp, client, agent = server_tools
    result = _call_tool(mcp, "ask_about_issues", question="What bugs are open?")
    assert result == "Issue #1 is a bug."
    agent.answer_question.assert_called_once()
    _, kwargs = agent.answer_question.call_args
    assert kwargs["question"] == "What bugs are open?"


def test_ask_about_issues_passes_filters(server_tools) -> None:
    mcp, client, agent = server_tools
    _call_tool(
        mcp,
        "ask_about_issues",
        question="What bugs?",
        state="opened",
        assignee_username="alice",
        labels="bug",
    )
    _, kwargs = client.get_issues.call_args
    assert kwargs["state"] == "opened"
    assert kwargs["assignee_username"] == "alice"
    assert kwargs["labels"] == "bug"
