"""Tests for config.py"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest
import yaml

from gitlab_issue_mcp.config import Config, load_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config_file(tmp_path: Path) -> Path:
    """Write a minimal valid config YAML and return its path."""
    data = {
        "gitlab_url": "https://gitlab.example.com",
        "gitlab_api_key": "glpat-test-token",
        "llm_base_url": "http://localhost:4000",
        "llm_model": "gpt-4o",
        "llm_api_key": "sk-test",
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data))
    return p


# ---------------------------------------------------------------------------
# load_config — happy path
# ---------------------------------------------------------------------------


def test_load_config_from_explicit_path(config_file: Path) -> None:
    cfg = load_config(str(config_file))
    assert cfg.gitlab_url == "https://gitlab.example.com"
    assert cfg.gitlab_api_key == "glpat-test-token"
    assert cfg.llm_base_url == "http://localhost:4000"
    assert cfg.llm_model == "gpt-4o"
    assert cfg.llm_api_key == "sk-test"


def test_load_config_defaults(config_file: Path) -> None:
    cfg = load_config(str(config_file))
    assert cfg.gitlab_project_id is None
    assert cfg.gitlab_group_id is None
    assert cfg.max_issues_per_query == 100
    assert cfg.max_issues_for_agent == 50


def test_load_config_with_optional_fields(tmp_path: Path) -> None:
    data = {
        "gitlab_url": "https://gitlab.example.com",
        "gitlab_api_key": "glpat-test",
        "llm_base_url": "http://localhost:4000",
        "llm_model": "llama3",
        "gitlab_project_id": 42,
        "gitlab_group_id": "my-org",
        "max_issues_per_query": 50,
        "max_issues_for_agent": 25,
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data))
    cfg = load_config(str(p))
    assert cfg.gitlab_project_id == 42
    assert cfg.gitlab_group_id == "my-org"
    assert cfg.max_issues_per_query == 50
    assert cfg.max_issues_for_agent == 25


# ---------------------------------------------------------------------------
# load_config — environment variable overrides
# ---------------------------------------------------------------------------


def test_env_override_gitlab_url(config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_URL", "https://override.example.com")
    cfg = load_config(str(config_file))
    assert cfg.gitlab_url == "https://override.example.com"


def test_env_override_api_key(config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_API_KEY", "glpat-override")
    cfg = load_config(str(config_file))
    assert cfg.gitlab_api_key == "glpat-override"


def test_env_override_llm_base_url(config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "http://myserver:8000")
    cfg = load_config(str(config_file))
    assert cfg.llm_base_url == "http://myserver:8000"


def test_env_override_llm_model(config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "mistral")
    cfg = load_config(str(config_file))
    assert cfg.llm_model == "mistral"


def test_env_override_llm_api_key(config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-env-override")
    cfg = load_config(str(config_file))
    assert cfg.llm_api_key == "sk-env-override"


# ---------------------------------------------------------------------------
# load_config — error cases
# ---------------------------------------------------------------------------


def test_load_config_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="config"):
        load_config(str(tmp_path / "nonexistent.yaml"))


def test_load_config_via_env_var(config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_MCP_CONFIG", str(config_file))
    # Unset any cwd config.yaml if present
    cfg = load_config()
    assert cfg.gitlab_url == "https://gitlab.example.com"


def test_load_config_missing_required_key(tmp_path: Path) -> None:
    # gitlab_url is missing
    data = {
        "gitlab_api_key": "glpat-test",
        "llm_base_url": "http://localhost:4000",
        "llm_model": "gpt-4o",
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data))
    with pytest.raises(ValueError, match="gitlab_url"):
        load_config(str(p))


def test_load_config_ignores_unknown_keys(tmp_path: Path) -> None:
    data = {
        "gitlab_url": "https://gitlab.example.com",
        "gitlab_api_key": "glpat-test",
        "llm_base_url": "http://localhost:4000",
        "llm_model": "gpt-4o",
        "unknown_extra_key": "should be ignored",
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data))
    cfg = load_config(str(p))
    assert cfg.gitlab_url == "https://gitlab.example.com"
