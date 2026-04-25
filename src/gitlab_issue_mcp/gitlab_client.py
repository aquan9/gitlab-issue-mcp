"""GitLab REST API client wrapper.

Wraps ``python-gitlab`` to provide a simple, dict-oriented interface for
fetching issues and related resources.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import gitlab
from gitlab.exceptions import GitlabError

logger = logging.getLogger(__name__)


class GitLabClient:
    """Thin wrapper around :mod:`gitlab` for issue retrieval.

    Parameters
    ----------
    url:
        Base URL of the GitLab instance (e.g. ``https://gitlab.com``).
    api_key:
        Personal access token with at least ``read_api`` scope.
    """

    def __init__(self, url: str, api_key: str) -> None:
        self._gl = gitlab.Gitlab(url=url, private_token=api_key)
        self._authenticate()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _authenticate(self) -> None:
        try:
            self._gl.auth()
            logger.info("Authenticated with GitLab at %s", self._gl.url)
        except GitlabError as exc:
            logger.warning("GitLab authentication check failed: %s", exc)

    # ------------------------------------------------------------------
    # Issues
    # ------------------------------------------------------------------

    def get_issues(
        self,
        project_id: Optional[int] = None,
        group_id: Optional[str] = None,
        state: Optional[str] = None,
        assignee_username: Optional[str] = None,
        author_username: Optional[str] = None,
        labels: Optional[str] = None,
        milestone: Optional[str] = None,
        search: Optional[str] = None,
        max_results: int = 100,
    ) -> List[Dict[str, Any]]:
        """Return a list of issues matching the given filters.

        At least one of *project_id* or *group_id* must be set, or the
        authenticated user's visible issues are returned.

        Parameters
        ----------
        project_id:
            Numeric GitLab project ID.
        group_id:
            Group ID or URL-encoded path (e.g. ``"my-org/my-group"``).
        state:
            ``"opened"``, ``"closed"``, or ``"all"`` (default: ``"opened"``).
        assignee_username:
            Filter by the assignee's GitLab username.
        author_username:
            Filter by the author's GitLab username.
        labels:
            Comma-separated list of label names.
        milestone:
            Milestone title to filter by.
        search:
            Full-text search across issue title and description.
        max_results:
            Hard cap on the number of issues returned (≤ 100).
        """
        params: Dict[str, Any] = {}
        if state:
            params["state"] = state
        if assignee_username:
            params["assignee_username"] = assignee_username
        if author_username:
            params["author_username"] = author_username
        if labels:
            params["labels"] = labels
        if milestone:
            params["milestone"] = milestone
        if search:
            params["search"] = search

        per_page = min(max_results, 100)

        try:
            if project_id:
                project = self._gl.projects.get(project_id)
                raw_issues = project.issues.list(
                    per_page=per_page, get_all=False, **params
                )
            elif group_id:
                group = self._gl.groups.get(group_id)
                raw_issues = group.issues.list(
                    per_page=per_page, get_all=False, **params
                )
            else:
                raw_issues = self._gl.issues.list(
                    per_page=per_page, get_all=False, **params
                )
        except GitlabError as exc:
            logger.error("Error fetching issues: %s", exc)
            raise

        return [_obj_to_dict(issue) for issue in raw_issues]

    # ------------------------------------------------------------------
    # Single issue
    # ------------------------------------------------------------------

    def get_issue(
        self,
        issue_iid: int,
        project_id: int,
    ) -> Dict[str, Any]:
        """Return a single issue by its project-scoped IID.

        Parameters
        ----------
        issue_iid:
            The issue number shown in the GitLab UI (project-scoped IID).
        project_id:
            Numeric GitLab project ID that owns the issue.
        """
        try:
            project = self._gl.projects.get(project_id)
            issue = project.issues.get(issue_iid)
            return _obj_to_dict(issue)
        except GitlabError as exc:
            logger.error("Error fetching issue %s: %s", issue_iid, exc)
            raise

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def get_user(self, username: str) -> Dict[str, Any]:
        """Return a GitLab user's public profile by username.

        Raises
        ------
        ValueError
            If no user with the given username exists.
        """
        try:
            users = self._gl.users.list(username=username)
        except GitlabError as exc:
            logger.error("Error fetching user '%s': %s", username, exc)
            raise

        if not users:
            raise ValueError(f"GitLab user '{username}' not found")

        return _obj_to_dict(users[0])

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def get_current_user(self) -> Dict[str, Any]:
        """Return the currently authenticated user's profile.

        Raises
        ------
        gitlab.exceptions.GitlabError
            If the API call fails (e.g. invalid token or network error).
        """
        try:
            user = self._gl.users.get_current()
            return _obj_to_dict(user)
        except GitlabError as exc:
            logger.error("Error fetching current user: %s", exc)
            raise

    def get_project(self, project_id: int) -> Dict[str, Any]:
        """Return metadata for a GitLab project.

        Parameters
        ----------
        project_id:
            Numeric GitLab project ID.
        """
        try:
            project = self._gl.projects.get(project_id)
            return _obj_to_dict(project)
        except GitlabError as exc:
            logger.error("Error fetching project %s: %s", project_id, exc)
            raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    """Convert a python-gitlab REST object to a plain dict."""
    if hasattr(obj, "asdict"):
        return obj.asdict()
    if hasattr(obj, "attributes"):
        return dict(obj.attributes)
    return dict(obj)
