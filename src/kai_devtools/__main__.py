"""Interface for ``python -m kai_devtools`` and the ``kai-devtools`` CLI.

Usage
-----
    kai-devtools --data-dir /path/to/kai-daemon/data

Options
-------
    --data-dir      Path to the daemon's data/ directory (required)
    --api-port      Port for the daemon action/status API [default: 9271]
    --api-host      Host for the daemon action/status API [default: 127.0.0.1]
    -v, --version   Show version and exit
"""

from __future__ import annotations

from argparse import ArgumentParser
from collections.abc import Sequence
from pathlib import Path

from . import __version__

__all__ = ["main"]


def main(args: Sequence[str] | None = None) -> None:
    """Entry point for the kai-devtools CLI."""
    parser = ArgumentParser(
        prog="kai-devtools",
        description="Observability panel for the kai-daemon (§13).",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=__version__,
    )
    parser.add_argument(
        "--data-dir",
        metavar="PATH",
        default=None,
        help=(
            "Path to the daemon's data/ directory.  "
            "Defaults to ./data relative to the current working directory."
        ),
    )
    parser.add_argument(
        "--api-port",
        metavar="PORT",
        type=int,
        default=9271,
        help="Port for the daemon action API (default: 9271).",
    )
    parser.add_argument(
        "--api-host",
        metavar="HOST",
        default="127.0.0.1",
        help="Host for the daemon action API (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--conv-url",
        metavar="URL",
        default=None,
        help="Base URL for the conversation server (default: http://localhost:9272).",
    )
    parsed = parser.parse_args(args)

    data_dir = (
        Path(parsed.data_dir) if parsed.data_dir is not None else Path.cwd() / "data"
    )
    base_url = f"http://{parsed.api_host}:{parsed.api_port}"

    # Lazy imports so that tests that only parse --version never import Textual.
    from ._action_client import ActionClient
    from ._app import DEFAULT_CONV_URL, KaiDevtoolsApp
    from ._reader import DaemonStateReader

    reader = DaemonStateReader(data_dir)
    client = ActionClient(base_url=base_url)
    conv_url = parsed.conv_url if parsed.conv_url is not None else DEFAULT_CONV_URL
    app = KaiDevtoolsApp(reader, client, conv_url=conv_url)
    app.run()


if __name__ == "__main__":
    main()
