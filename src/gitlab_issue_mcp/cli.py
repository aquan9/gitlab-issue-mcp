"""Command-line interface for gitlab-issue-mcp."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

import click
from mcp.types import TextContent

from .config import load_config
from .gitlab_client import GitLabClient
from .server import create_server
from gitlab.exceptions import GitlabAuthenticationError, GitlabError

logger = logging.getLogger(__name__)


def _load_config_or_exit(ctx: click.Context):
    """Load configuration or exit the CLI with a helpful error message."""
    config_path = ctx.obj.get("config_path")
    try:
        return load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Error loading config: {exc}", err=True)
        sys.exit(1)


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


# ---------------------------------------------------------------------------
# MCP tool introspection / invocation
# ---------------------------------------------------------------------------


@cli.command("list-tools")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit the tool catalogue as a JSON document (including input schemas).",
)
@click.pass_context
def list_tools(ctx: click.Context, as_json: bool) -> None:
    """List the MCP tools (endpoints) exposed by this server.

    Useful for discovering which endpoints can be exercised with
    ``gitlab-issue-mcp call-tool``.
    """
    config = _load_config_or_exit(ctx)
    mcp = create_server(config)

    tools = asyncio.run(mcp.list_tools())

    if as_json:
        payload = [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.inputSchema,
            }
            for t in tools
        ]
        click.echo(json.dumps(payload, indent=2, default=str))
        return

    if not tools:
        click.echo("No MCP tools registered.")
        return

    click.echo(f"Available MCP tools ({len(tools)}):")
    for tool in tools:
        description = (tool.description or "").strip().splitlines()
        summary = description[0] if description else ""
        click.echo(f"  - {tool.name}: {summary}")
        properties = (tool.inputSchema or {}).get("properties") or {}
        required = set((tool.inputSchema or {}).get("required") or [])
        for arg_name, arg_schema in properties.items():
            arg_type = arg_schema.get("type", "any")
            marker = "required" if arg_name in required else "optional"
            click.echo(f"      • {arg_name} ({arg_type}, {marker})")


@cli.command("call-tool")
@click.argument("name")
@click.option(
    "--arg",
    "args",
    multiple=True,
    metavar="KEY=VALUE",
    help=(
        "Pass an argument to the tool. May be repeated. Values are parsed as "
        "JSON when possible (e.g. numbers, booleans, JSON arrays/objects), "
        "otherwise treated as strings."
    ),
)
@click.option(
    "--json",
    "json_args",
    default=None,
    metavar="JSON",
    help=(
        "Pass arguments as a single JSON object, e.g. "
        "'{\"state\": \"opened\", \"project_id\": 42}'. Use '-' to read JSON "
        "from stdin. Cannot be combined with --arg."
    ),
)
@click.option(
    "--raw",
    is_flag=True,
    help="Print only the raw tool output (no header). Easier to pipe.",
)
@click.pass_context
def call_tool(
    ctx: click.Context,
    name: str,
    args: tuple[str, ...],
    json_args: str | None,
    raw: bool,
) -> None:
    """Invoke an MCP tool by NAME and print its result.

    Examples
    --------

    \b
      gitlab-issue-mcp call-tool list_issues --arg state=opened
      gitlab-issue-mcp call-tool get_issue --arg issue_iid=42
      gitlab-issue-mcp call-tool list_issues --json '{"state": "closed"}'
      echo '{"username": "alice"}' | gitlab-issue-mcp call-tool get_user_profile --json -
    """
    if args and json_args is not None:
        click.echo("Error: --arg and --json are mutually exclusive.", err=True)
        sys.exit(2)

    arguments: dict[str, Any] = {}
    if json_args is not None:
        raw_json = sys.stdin.read() if json_args == "-" else json_args
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            click.echo(f"Error: --json value is not valid JSON: {exc}", err=True)
            sys.exit(2)
        if not isinstance(parsed, dict):
            click.echo("Error: --json value must be a JSON object.", err=True)
            sys.exit(2)
        arguments = parsed
    else:
        for entry in args:
            if "=" not in entry:
                click.echo(
                    f"Error: --arg expects KEY=VALUE, got: {entry!r}", err=True
                )
                sys.exit(2)
            key, _, value = entry.partition("=")
            key = key.strip()
            if not key:
                click.echo(f"Error: --arg has empty key: {entry!r}", err=True)
                sys.exit(2)
            try:
                arguments[key] = json.loads(value)
            except json.JSONDecodeError:
                arguments[key] = value

    config = _load_config_or_exit(ctx)
    mcp = create_server(config)

    # Validate the tool name up-front so users get a clear error and a hint
    # about which tools are available.
    available = asyncio.run(mcp.list_tools())
    available_names = [t.name for t in available]
    if name not in available_names:
        click.echo(
            f"Error: unknown tool {name!r}. Available tools: "
            f"{', '.join(available_names)}",
            err=True,
        )
        sys.exit(2)

    try:
        content, structured = asyncio.run(mcp.call_tool(name, arguments))
    except Exception as exc:  # noqa: BLE001 — surface any tool failure to the user
        click.echo(f"Error invoking tool {name!r}: {exc}", err=True)
        sys.exit(1)

    if not raw:
        click.echo(f"--- Result of {name} ---")

    # Prefer the human-readable text content blocks; fall back to the
    # structured result for tools that return non-text payloads.
    if content:
        for block in content:
            if isinstance(block, TextContent):
                click.echo(block.text)
            else:
                click.echo(json.dumps(block.model_dump(), indent=2, default=str))
    elif structured is not None:
        click.echo(json.dumps(structured, indent=2, default=str))
