"""Entry point for ``python -m gitlab_issue_mcp`` and the installed script."""

from __future__ import annotations

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Load config, create the MCP server, and start serving over stdio."""
    from .config import load_config
    from .server import create_server

    try:
        config = load_config()
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(1)

    mcp = create_server(config)

    transport = config.mcp_transport
    if transport not in ("stdio", "sse", "streamable-http"):
        logger.error(
            "Invalid mcp_transport %r; expected one of stdio, sse, streamable-http",
            transport,
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


if __name__ == "__main__":
    main()
