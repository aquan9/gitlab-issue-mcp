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

    logger.info("Starting gitlab-issue-mcp server (stdio transport)…")
    mcp.run()


if __name__ == "__main__":
    main()
