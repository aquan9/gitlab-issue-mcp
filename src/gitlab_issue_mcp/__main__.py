"""Entry point for ``python -m gitlab_issue_mcp`` and the installed script."""

from __future__ import annotations

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


def main() -> None:
    """CLI entry point – delegates to the :mod:`click` command group."""
    from .cli import cli

    cli()


if __name__ == "__main__":
    main()
