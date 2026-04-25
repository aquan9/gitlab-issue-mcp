"""Command-line interface for gitlab-issue-mcp."""

from __future__ import annotations

import logging
import sys

import click

from .config import load_config
from .gitlab_client import GitLabClient
from .server import create_server
from gitlab.exceptions import GitlabAuthenticationError, GitlabError

logger = logging.getLogger(__name__)


@click.group()
@click.option(
    "--config",
    default=None,
    envvar="GITLAB_MCP_CONFIG",
    metavar="FILE",
    help="Path to the YAML configuration file.",
)
@click.pass_context
def cli(ctx: click.Context, config: str | None) -> None:
    """GitLab Issue MCP Server.

    Run 'gitlab-issue-mcp COMMAND --help' for help on a specific command.
    """
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


@cli.command()
@click.pass_context
def serve(ctx: click.Context) -> None:
    """Start the MCP server."""
    config_path = ctx.obj.get("config_path")

    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    mcp = create_server(config)

    transport = config.mcp_transport
    if transport not in ("stdio", "sse", "streamable-http"):
        click.echo(
            f"Error: Invalid mcp_transport {transport!r}; "
            "expected one of stdio, sse, streamable-http",
            err=True,
        )
        sys.exit(1)

    if transport == "stdio":
        logger.info("Starting gitlab-issue-mcp server (stdio transport)…")
    else:
        logger.info(
            "Starting gitlab-issue-mcp server (%s transport) on %s:%s…",
            transport,
            config.mcp_host,
            config.mcp_port,
        )
    mcp.run(transport=transport)


@cli.command("check-connection")
@click.pass_context
def check_connection(ctx: click.Context) -> None:
    """Test connectivity to the configured GitLab server.

    Loads the configuration, authenticates with GitLab, and prints
    the currently authenticated user's details on success.

    Exits with a non-zero status code if the connection fails.
    """
    config_path = ctx.obj.get("config_path")

    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Error loading config: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Connecting to {config.gitlab_url} …")

    try:
        client = GitLabClient(config.gitlab_url, config.gitlab_api_key)
        user = client.get_current_user()
    except GitlabAuthenticationError as exc:
        click.echo(f"Authentication failed: {exc}", err=True)
        sys.exit(1)
    except GitlabError as exc:
        click.echo(f"Connection failed: {exc}", err=True)
        sys.exit(1)

    username = user.get("username", "unknown")
    name = user.get("name", "")
    click.echo(f"✓ Successfully connected to {config.gitlab_url}")
    click.echo(f"  Authenticated as: {username} ({name})")
