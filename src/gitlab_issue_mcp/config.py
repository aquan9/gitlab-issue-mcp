"""Configuration loading for gitlab-issue-mcp.

Configuration is read from a YAML file whose path is resolved in this order:
1. Path supplied directly to :func:`load_config`.
2. The path in the ``GITLAB_MCP_CONFIG`` environment variable.
3. ``config.yaml`` in the current working directory.
4. ``~/.config/gitlab-issue-mcp/config.yaml``.

Any value in the YAML file can also be overridden with the following
environment variables:

- ``GITLAB_URL``
- ``GITLAB_API_KEY``
- ``LLM_BASE_URL``
- ``LLM_MODEL``
- ``LLM_API_KEY``
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_STATIC_DEFAULT_PATHS = [
    Path("config.yaml"),
    Path.home() / ".config" / "gitlab-issue-mcp" / "config.yaml",
]


@dataclass
class Config:
    """Validated application configuration."""

    # --- GitLab ---------------------------------------------------------------
    gitlab_url: str
    """Base URL of the GitLab instance (e.g. ``https://gitlab.com``)."""

    gitlab_api_key: str
    """Personal access token with at least ``read_api`` scope."""

    # --- LLM ------------------------------------------------------------------
    llm_base_url: str
    """Base URL for the OpenAI-compatible LLM endpoint (e.g. LiteLLM)."""

    llm_model: str
    """Model name to pass to the LLM provider."""

    llm_api_key: Optional[str] = None
    """API key for the LLM provider.  Set to ``"NA"`` for keyless local setups."""

    # --- GitLab scope ---------------------------------------------------------
    gitlab_project_id: Optional[int] = None
    """Default project ID used when none is supplied per-call."""

    gitlab_group_id: Optional[str] = None
    """Default group ID/path used when no project is configured."""

    # --- Limits ---------------------------------------------------------------
    max_issues_per_query: int = 100
    """Maximum issues returned by each GitLab API call."""

    max_issues_for_agent: int = 50
    """Maximum issues forwarded to the AutoGen agent to avoid context overflow."""


def load_config(path: Optional[str] = None) -> Config:
    """Load and return a :class:`Config` from a YAML file.

    Parameters
    ----------
    path:
        Explicit path to the YAML config file.  When *None* the default
        search order is used (see module docstring).

    Raises
    ------
    FileNotFoundError
        If no config file can be located.
    ValueError
        If required fields are missing after applying env-var overrides.
    """
    config_path = _resolve_path(path)

    with open(config_path) as fh:
        data: dict = yaml.safe_load(fh) or {}

    logger.info("Loaded config from %s", config_path)

    # Environment variables take precedence over file values.
    _apply_env_overrides(data)

    # Keep only keys that belong to Config to avoid unexpected kwarg errors.
    known_fields = {f.name for f in fields(Config)}
    filtered = {k: v for k, v in data.items() if k in known_fields}

    _validate_required(filtered)
    return Config(**filtered)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_path(explicit: Optional[str]) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")
        return p

    # Build the candidate list at call time so env-var changes are respected.
    candidates = []
    env_path = os.environ.get("GITLAB_MCP_CONFIG", "")
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(_STATIC_DEFAULT_PATHS)

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        "No configuration file found.  Create a config.yaml file (see "
        "config.example.yaml) or set the GITLAB_MCP_CONFIG environment variable."
    )


def _apply_env_overrides(data: dict) -> None:
    """Overwrite *data* in-place with any matching environment variables."""
    mapping = {
        "GITLAB_URL": "gitlab_url",
        "GITLAB_API_KEY": "gitlab_api_key",
        "LLM_BASE_URL": "llm_base_url",
        "LLM_MODEL": "llm_model",
        "LLM_API_KEY": "llm_api_key",
    }
    for env_var, key in mapping.items():
        value = os.environ.get(env_var)
        if value:
            data[key] = value


def _validate_required(data: dict) -> None:
    required = ("gitlab_url", "gitlab_api_key", "llm_base_url", "llm_model")
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise ValueError(
            f"Missing required configuration keys: {', '.join(missing)}"
        )
