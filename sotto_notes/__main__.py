"""Command-line entry point: ``python -m sotto_notes``."""

from __future__ import annotations

import argparse
import threading
import webbrowser

from . import __version__, config, server
from .providers import PROVIDERS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sotto-notes",
        description="Local speech-to-notes: audio in, editable timestamped notes out.",
    )
    parser.add_argument("--host", default=config.HOST, help="bind address")
    parser.add_argument("--port", type=int, default=config.PORT, help="port")
    parser.add_argument(
        "--no-browser", action="store_true", help="do not open a browser tab"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="print provider availability and exit",
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config.ensure_dirs()

    if args.check:
        print(f"sotto-notes {__version__}")
        print(f"data dir: {config.DATA_DIR}")
        for provider in PROVIDERS.values():
            status = provider.status()
            flag = "ready" if status["available"] else "off"
            print(f"  [{flag:5}] {status['label']}: {status['detail']}")
        return 0

    if not args.no_browser:
        url = f"http://{args.host}:{args.port}"
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    server.serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
