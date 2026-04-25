"""Tests for agent.py"""

from __future__ import annotations

import json
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from gitlab_issue_mcp.agent import IssueQAAgent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def llm_config() -> Dict[str, Any]:
    return {
        "config_list": [
            {"model": "gpt-4o", "api_key": "sk-test", "base_url": "http://localhost:4000"}
        ],
        "temperature": 0,
    }


@pytest.fixture()
def sample_issues() -> List[Dict[str, Any]]:
    return [
        {
            "iid": 1,
            "title": "Login page crashes on mobile",
            "state": "opened",
            "assignees": [{"username": "alice"}],
            "author": {"username": "bob"},
            "labels": ["bug", "mobile"],
            "milestone": {"title": "v1.2"},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-05T00:00:00Z",
            "description": "When the user taps login on iOS the app crashes.",
            "web_url": "https://gitlab.example.com/proj/-/issues/1",
        },
        {
            "iid": 2,
            "title": "Add dark mode",
            "state": "opened",
            "assignees": [{"username": "carol"}],
            "author": {"username": "alice"},
            "labels": ["feature"],
            "milestone": None,
            "created_at": "2024-01-10T00:00:00Z",
            "updated_at": "2024-01-11T00:00:00Z",
            "description": "Users have requested a dark mode option.",
            "web_url": "https://gitlab.example.com/proj/-/issues/2",
        },
    ]


# ---------------------------------------------------------------------------
# IssueQAAgent._format_issues
# ---------------------------------------------------------------------------


def test_format_issues_empty() -> None:
    agent = IssueQAAgent.__new__(IssueQAAgent)
    result = agent._format_issues([])
    assert result == "No issues found."


def test_format_issues_contains_title(sample_issues: List[Dict[str, Any]]) -> None:
    agent = IssueQAAgent.__new__(IssueQAAgent)
    result = agent._format_issues(sample_issues)
    assert "Login page crashes on mobile" in result
    assert "Add dark mode" in result


def test_format_issues_truncates_description(sample_issues: List[Dict[str, Any]]) -> None:
    long_desc = "x" * 500
    sample_issues[0]["description"] = long_desc
    agent = IssueQAAgent.__new__(IssueQAAgent)
    result = agent._format_issues(sample_issues)
    # Description truncated at 300 chars in the JSON
    parsed = [json.loads(line) for line in result.splitlines()]
    assert len(parsed[0]["description"]) == 300


def test_format_issues_handles_none_fields() -> None:
    issue = {
        "iid": 3,
        "title": "Minimal issue",
        "state": "closed",
        "assignees": None,
        "author": None,
        "labels": None,
        "milestone": None,
        "description": None,
        "web_url": None,
        "created_at": None,
        "updated_at": None,
    }
    agent = IssueQAAgent.__new__(IssueQAAgent)
    result = agent._format_issues([issue])
    parsed = json.loads(result)
    assert parsed["iid"] == 3
    assert parsed["assignees"] == []
    assert parsed["description"] == ""


# ---------------------------------------------------------------------------
# IssueQAAgent.answer_question — mocked AutoGen
# ---------------------------------------------------------------------------


def _mock_chat(user_proxy: MagicMock, assistant: MagicMock, answer: str) -> None:
    """Simulate what AutoGen stores after a one-round conversation."""
    user_proxy.chat_messages = {
        assistant: [
            {"role": "user", "content": "the question"},
            {"role": "assistant", "content": answer},
        ]
    }


@patch("gitlab_issue_mcp.agent.autogen.AssistantAgent")
@patch("gitlab_issue_mcp.agent.autogen.UserProxyAgent")
def test_answer_question_returns_assistant_response(
    MockUserProxy: MagicMock,
    MockAssistant: MagicMock,
    llm_config: Dict[str, Any],
    sample_issues: List[Dict[str, Any]],
) -> None:
    expected_answer = "Issue #1 is a bug on mobile assigned to alice."

    assistant_instance = MockAssistant.return_value
    user_proxy_instance = MockUserProxy.return_value

    def fake_initiate_chat(assistant, message, clear_history):
        _mock_chat(user_proxy_instance, assistant, expected_answer)

    user_proxy_instance.initiate_chat.side_effect = fake_initiate_chat

    agent = IssueQAAgent(llm_config)
    result = agent.answer_question("What is issue 1 about?", sample_issues)

    assert result == expected_answer
    user_proxy_instance.initiate_chat.assert_called_once()


@patch("gitlab_issue_mcp.agent.autogen.AssistantAgent")
@patch("gitlab_issue_mcp.agent.autogen.UserProxyAgent")
def test_answer_question_truncates_issues(
    MockUserProxy: MagicMock,
    MockAssistant: MagicMock,
    llm_config: Dict[str, Any],
    sample_issues: List[Dict[str, Any]],
) -> None:
    """Only max_issues issues should be forwarded to the agent."""
    captured_prompts: list = []

    assistant_instance = MockAssistant.return_value
    user_proxy_instance = MockUserProxy.return_value

    def fake_initiate_chat(assistant, message, clear_history):
        captured_prompts.append(message)
        _mock_chat(user_proxy_instance, assistant, "answer")

    user_proxy_instance.initiate_chat.side_effect = fake_initiate_chat

    # Create 10 issues but limit to 1
    many_issues = sample_issues * 5  # 10 issues
    agent = IssueQAAgent(llm_config)
    agent.answer_question("anything", many_issues, max_issues=1)

    prompt = captured_prompts[0]
    # Only the first issue title should appear
    assert "Login page crashes on mobile" in prompt
    # The second issue should NOT appear (only 1 allowed)
    assert "Add dark mode" not in prompt


@patch("gitlab_issue_mcp.agent.autogen.AssistantAgent")
@patch("gitlab_issue_mcp.agent.autogen.UserProxyAgent")
def test_answer_question_no_agent_response(
    MockUserProxy: MagicMock,
    MockAssistant: MagicMock,
    llm_config: Dict[str, Any],
    sample_issues: List[Dict[str, Any]],
) -> None:
    """When no assistant message is found, return the fallback string."""
    assistant_instance = MockAssistant.return_value
    user_proxy_instance = MockUserProxy.return_value
    user_proxy_instance.chat_messages = {assistant_instance: []}
    user_proxy_instance.initiate_chat.return_value = None

    agent = IssueQAAgent(llm_config)
    result = agent.answer_question("anything", sample_issues)

    assert "did not produce" in result


@patch("gitlab_issue_mcp.agent.autogen.AssistantAgent")
@patch("gitlab_issue_mcp.agent.autogen.UserProxyAgent")
def test_answer_question_propagates_autogen_error(
    MockUserProxy: MagicMock,
    MockAssistant: MagicMock,
    llm_config: Dict[str, Any],
    sample_issues: List[Dict[str, Any]],
) -> None:
    user_proxy_instance = MockUserProxy.return_value
    user_proxy_instance.initiate_chat.side_effect = Exception("LLM unreachable")

    agent = IssueQAAgent(llm_config)
    with pytest.raises(RuntimeError, match="Agent conversation failed"):
        agent.answer_question("anything", sample_issues)
