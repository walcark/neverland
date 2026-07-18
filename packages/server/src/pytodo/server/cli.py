"""The ``pytodo-server`` command.

A small argparse CLI to manage the server process, separate from the ``todo``
command (which manages todos). Only ``run`` exists so far; ``setup`` and
``install`` (systemd) land with the deployment step.
"""

from __future__ import annotations

import argparse
import sys

from .config import ConfigError, ServerConfig


def _run(_args: argparse.Namespace) -> int:
    """Start the uvicorn server from the environment config."""
    import uvicorn

    from .app import create_app

    try:
        config = ServerConfig.from_env()
    except ConfigError as exc:
        print(f"pytodo-server: {exc}", file=sys.stderr)
        return 2

    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pytodo-server", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("run", help="Run the web server (foreground).")
    run.set_defaults(func=_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``pytodo-server`` console script."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
