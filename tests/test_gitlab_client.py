"""Tests for gitlab_client.py"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from gitlab_issue_mcp.gitlab_client import GitLabClient, _obj_to_dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_issue(**kwargs: Any) -> MagicMock:
    """Return a mock python-gitlab issue object."""
    defaults = {
        "iid": 1,
        "title": "Test issue",
        "state": "opened",
        "assignees": [],
        "author": {"username": "alice"},
        "labels": [],
        "milestone": None,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "description": "Some description",
        "web_url": "https://gitlab.example.com/proj/-/issues/1",
    }
    defaults.update(kwargs)

    obj = MagicMock()
    obj.asdict.return_value = defaults
    obj.attributes = defaults
    return obj


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_gl():
    """Patch python-gitlab.Gitlab so no real HTTP calls are made."""
    with patch("gitlab_issue_mcp.gitlab_client.gitlab.Gitlab") as MockGitlab:
        instance = MockGitlab.return_value
        instance.auth.return_value = None
        yield instance


@pytest.fixture()
def client(mock_gl: MagicMock) -> GitLabClient:
    return GitLabClient("https://gitlab.example.com", "glpat-test")


# ---------------------------------------------------------------------------
# _obj_to_dict helper
# ---------------------------------------------------------------------------


def test_obj_to_dict_with_asdict() -> None:
    obj = MagicMock()
    obj.asdict.return_value = {"key": "value"}
    result = _obj_to_dict(obj)
    assert result == {"key": "value"}


def test_obj_to_dict_with_attributes() -> None:
    obj = MagicMock(spec=[])  # no asdict
    obj.attributes = {"key": "value"}
    result = _obj_to_dict(obj)
    assert result == {"key": "value"}


# ---------------------------------------------------------------------------
# GitLabClient.get_issues
# ---------------------------------------------------------------------------


def test_get_issues_project_level(client: GitLabClient, mock_gl: MagicMock) -> None:
    issue = _make_issue(iid=5, title="Bug fix")
    project = MagicMock()
    project.issues.list.return_value = [issue]
    mock_gl.projects.get.return_value = project

    results = client.get_issues(project_id=99)

    mock_gl.projects.get.assert_called_once_with(99)
    project.issues.list.assert_called_once()
    assert len(results) == 1
    assert results[0]["iid"] == 5


def test_get_issues_group_level(client: GitLabClient, mock_gl: MagicMock) -> None:
    issue = _make_issue(iid=3)
    group = MagicMock()
    group.issues.list.return_value = [issue]
    mock_gl.groups.get.return_value = group

    results = client.get_issues(group_id="my-group")

    mock_gl.groups.get.assert_called_once_with("my-group")
    assert len(results) == 1


def test_get_issues_global(client: GitLabClient, mock_gl: MagicMock) -> None:
    mock_gl.issues.list.return_value = [_make_issue()]
    results = client.get_issues()
    mock_gl.issues.list.assert_called_once()
    assert len(results) == 1


def test_get_issues_filters_forwarded(client: GitLabClient, mock_gl: MagicMock) -> None:
    project = MagicMock()
    project.issues.list.return_value = []
    mock_gl.projects.get.return_value = project

    client.get_issues(
        project_id=1,
        state="opened",
        assignee_username="bob",
        labels="bug,urgent",
        search="crash",
    )

    _, kwargs = project.issues.list.call_args
    assert kwargs["state"] == "opened"
    assert kwargs["assignee_username"] == "bob"
    assert kwargs["labels"] == "bug,urgent"
    assert kwargs["search"] == "crash"


def test_get_issues_max_results_capped(client: GitLabClient, mock_gl: MagicMock) -> None:
    project = MagicMock()
    project.issues.list.return_value = []
    mock_gl.projects.get.return_value = project

    client.get_issues(project_id=1, max_results=200)

    _, kwargs = project.issues.list.call_args
    assert kwargs["per_page"] == 100  # capped at 100


def test_get_issues_raises_on_gitlab_error(client: GitLabClient, mock_gl: MagicMock) -> None:
    from gitlab.exceptions import GitlabError

    mock_gl.issues.list.side_effect = GitlabError("API error")
    with pytest.raises(GitlabError):
        client.get_issues()


# ---------------------------------------------------------------------------
# GitLabClient.get_issue
# ---------------------------------------------------------------------------


def test_get_issue(client: GitLabClient, mock_gl: MagicMock) -> None:
    issue = _make_issue(iid=7, title="Specific issue")
    project = MagicMock()
    project.issues.get.return_value = issue
    mock_gl.projects.get.return_value = project

    result = client.get_issue(issue_iid=7, project_id=42)

    mock_gl.projects.get.assert_called_once_with(42)
    project.issues.get.assert_called_once_with(7)
    assert result["iid"] == 7


# ---------------------------------------------------------------------------
# GitLabClient.get_user
# ---------------------------------------------------------------------------


def test_get_user_found(client: GitLabClient, mock_gl: MagicMock) -> None:
    user = MagicMock()
    user.asdict.return_value = {"username": "alice", "id": 1}
    mock_gl.users.list.return_value = [user]

    result = client.get_user("alice")
    assert result["username"] == "alice"


def test_get_user_not_found(client: GitLabClient, mock_gl: MagicMock) -> None:
    mock_gl.users.list.return_value = []
    with pytest.raises(ValueError, match="not found"):
        client.get_user("ghost")


# ---------------------------------------------------------------------------
# GitLabClient.get_project
# ---------------------------------------------------------------------------


def test_get_project(client: GitLabClient, mock_gl: MagicMock) -> None:
    project = MagicMock()
    project.asdict.return_value = {"id": 99, "name": "My Project"}
    mock_gl.projects.get.return_value = project

    result = client.get_project(99)
    assert result["id"] == 99
