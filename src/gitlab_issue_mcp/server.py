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
import secrets
from typing import Any, Dict, Optional

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl

from .agent import IssueQAAgent
from .config import Config
from .gitlab_client import GitLabClient

logger = logging.getLogger(__name__)


class StaticTokenVerifier(TokenVerifier):
    """Verify bearer tokens against a single shared secret.

    A request is authorized when its ``Authorization: Bearer <token>``
    header matches the configured token exactly.  Comparison uses
    :func:`secrets.compare_digest` to avoid timing leaks.
    """

    def __init__(self, expected_token: str, *, client_id: str = "gitlab-issue-mcp") -> None:
        if not expected_token:
            raise ValueError("StaticTokenVerifier requires a non-empty token")
        self._expected_token = expected_token
        self._client_id = client_id

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        if not token or not secrets.compare_digest(token, self._expected_token):
            return None
        return AccessToken(token=token, client_id=self._client_id, scopes=[])


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

    fastmcp_kwargs: Dict[str, Any] = {
        "instructions": (
            "MCP server that exposes GitLab issues and an AI-powered "
            "question-answering service.  Use list_issues / get_issue for "
            "raw data access, and ask_about_issues for natural-language Q&A."
        ),
        "host": config.mcp_host,
        "port": config.mcp_port,
    }

    # Bearer token authentication is only meaningful for HTTP transports.
    # For the stdio transport the channel is a private pipe and FastMCP's
    # auth middleware is never reached, so we skip wiring it up.
    if config.mcp_bearer_token and config.mcp_transport != "stdio":
        resource_url = (
            config.mcp_resource_server_url
            or f"http://{config.mcp_host}:{config.mcp_port}"
        )
        fastmcp_kwargs["token_verifier"] = StaticTokenVerifier(config.mcp_bearer_token)
        fastmcp_kwargs["auth"] = AuthSettings(
            issuer_url=AnyHttpUrl(resource_url),
            resource_server_url=AnyHttpUrl(resource_url),
        )
        logger.info("Bearer token authentication enabled for MCP HTTP transport")
    elif config.mcp_bearer_token and config.mcp_transport == "stdio":
        logger.warning(
            "mcp_bearer_token is set but transport is 'stdio'; bearer auth "
            "is only applied to HTTP transports and will be ignored."
        )

    mcp = FastMCP("gitlab-issue-mcp", **fastmcp_kwargs)

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
