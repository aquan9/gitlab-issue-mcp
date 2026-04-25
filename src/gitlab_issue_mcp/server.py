"""FastMCP server exposing GitLab issue tools and AI-powered Q&A.

Tools exposed
-------------
list_issues
    List GitLab issues with rich filtering options.
get_issue
    Retrieve a single issue by its project-scoped IID.
get_user_issues
    Retrieve all issues assigned to a specific GitLab user.
get_user_profile
    Look up a GitLab user's public profile.
get_project_info
    Retrieve metadata for a GitLab project.
ask_about_issues
    Ask a natural-language question; an AutoGen agent analyses the
    matching issues and returns a human-readable answer.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

from .agent import IssueQAAgent
from .config import Config
from .gitlab_client import GitLabClient

logger = logging.getLogger(__name__)


def create_server(config: Config) -> FastMCP:
    """Construct and return a configured :class:`FastMCP` instance.

    Parameters
    ----------
    config:
        Validated application configuration.
    """
    gitlab_client = GitLabClient(config.gitlab_url, config.gitlab_api_key)

    llm_config: Dict[str, Any] = {
        "config_list": [
            {
                "model": config.llm_model,
                "api_key": config.llm_api_key or "NA",
                "base_url": config.llm_base_url,
            }
        ],
        "temperature": 0,
    }
    qa_agent = IssueQAAgent(llm_config)

    mcp = FastMCP(
        "gitlab-issue-mcp",
        instructions=(
            "MCP server that exposes GitLab issues and an AI-powered "
            "question-answering service.  Use list_issues / get_issue for "
            "raw data access, and ask_about_issues for natural-language Q&A."
        ),
    )

    # ------------------------------------------------------------------
    # Tool: list_issues
    # ------------------------------------------------------------------

    @mcp.tool()
    def list_issues(
        state: Optional[str] = None,
        assignee_username: Optional[str] = None,
        author_username: Optional[str] = None,
        labels: Optional[str] = None,
        milestone: Optional[str] = None,
        search: Optional[str] = None,
        project_id: Optional[int] = None,
        group_id: Optional[str] = None,
    ) -> str:
        """List GitLab issues with optional filtering.

        Parameters
        ----------
        state:
            ``"opened"``, ``"closed"``, or ``"all"``.
        assignee_username:
            Return only issues assigned to this GitLab username.
        author_username:
            Return only issues created by this GitLab username.
        labels:
            Comma-separated label names to filter by.
        milestone:
            Milestone title to filter by.
        search:
            Full-text search across issue title and description.
        project_id:
            Override the default project ID from the configuration.
        group_id:
            Override the default group ID from the configuration.
        """
        issues = gitlab_client.get_issues(
            project_id=project_id or config.gitlab_project_id,
            group_id=group_id or config.gitlab_group_id,
            state=state,
            assignee_username=assignee_username,
            author_username=author_username,
            labels=labels,
            milestone=milestone,
            search=search,
            max_results=config.max_issues_per_query,
        )
        return json.dumps(issues, indent=2, default=str)

    # ------------------------------------------------------------------
    # Tool: get_issue
    # ------------------------------------------------------------------

    @mcp.tool()
    def get_issue(
        issue_iid: int,
        project_id: Optional[int] = None,
    ) -> str:
        """Get detailed information about a specific GitLab issue.

        Parameters
        ----------
        issue_iid:
            The issue number shown in the GitLab UI (project-scoped IID).
        project_id:
            Override the default project ID from the configuration.
        """
        proj_id = project_id or config.gitlab_project_id
        if not proj_id:
            return json.dumps(
                {"error": "project_id is required but was not provided and is not set in config."},
                indent=2,
            )

        issue = gitlab_client.get_issue(
            issue_iid=issue_iid,
            project_id=proj_id,
        )
        return json.dumps(issue, indent=2, default=str)

    # ------------------------------------------------------------------
    # Tool: get_user_issues
    # ------------------------------------------------------------------

    @mcp.tool()
    def get_user_issues(
        username: str,
        state: Optional[str] = None,
        project_id: Optional[int] = None,
        group_id: Optional[str] = None,
    ) -> str:
        """Get all GitLab issues assigned to a specific user.

        Parameters
        ----------
        username:
            GitLab username of the assignee.
        state:
            ``"opened"``, ``"closed"``, or ``"all"``.
        project_id:
            Override the default project ID from the configuration.
        group_id:
            Override the default group ID from the configuration.
        """
        issues = gitlab_client.get_issues(
            project_id=project_id or config.gitlab_project_id,
            group_id=group_id or config.gitlab_group_id,
            assignee_username=username,
            state=state,
            max_results=config.max_issues_per_query,
        )
        return json.dumps(issues, indent=2, default=str)

    # ------------------------------------------------------------------
    # Tool: get_user_profile
    # ------------------------------------------------------------------

    @mcp.tool()
    def get_user_profile(username: str) -> str:
        """Get the public GitLab profile for a user.

        Parameters
        ----------
        username:
            GitLab username to look up.
        """
        user = gitlab_client.get_user(username)
        return json.dumps(user, indent=2, default=str)

    # ------------------------------------------------------------------
    # Tool: get_project_info
    # ------------------------------------------------------------------

    @mcp.tool()
    def get_project_info(project_id: Optional[int] = None) -> str:
        """Get metadata for a GitLab project.

        Parameters
        ----------
        project_id:
            Override the default project ID from the configuration.
        """
        proj_id = project_id or config.gitlab_project_id
        if not proj_id:
            return json.dumps(
                {"error": "project_id is required but was not provided and is not set in config."},
                indent=2,
            )

        project = gitlab_client.get_project(proj_id)
        return json.dumps(project, indent=2, default=str)

    # ------------------------------------------------------------------
    # Tool: ask_about_issues
    # ------------------------------------------------------------------

    @mcp.tool()
    def ask_about_issues(
        question: str,
        state: Optional[str] = None,
        assignee_username: Optional[str] = None,
        labels: Optional[str] = None,
        project_id: Optional[int] = None,
        group_id: Optional[str] = None,
    ) -> str:
        """Ask a natural-language question about GitLab issues.

        An AutoGen agent will load the relevant issues, analyse them, and
        return a human-readable answer.

        Examples
        --------
        - "Which issues are currently blocking the v2.0 release?"
        - "Summarise the open bugs assigned to alice"
        - "What features are planned for the next milestone?"
        - "How many issues were closed last week?"

        Parameters
        ----------
        question:
            The natural-language question to answer.
        state:
            Pre-filter issues by state before passing to the agent
            (``"opened"``, ``"closed"``, or ``"all"``).
        assignee_username:
            Pre-filter issues by assignee before passing to the agent.
        labels:
            Comma-separated labels to pre-filter issues.
        project_id:
            Override the default project ID from the configuration.
        group_id:
            Override the default group ID from the configuration.
        """
        issues = gitlab_client.get_issues(
            project_id=project_id or config.gitlab_project_id,
            group_id=group_id or config.gitlab_group_id,
            state=state,
            assignee_username=assignee_username,
            labels=labels,
            max_results=config.max_issues_per_query,
        )

        return qa_agent.answer_question(
            question=question,
            issues=issues,
            max_issues=config.max_issues_for_agent,
        )

    return mcp
