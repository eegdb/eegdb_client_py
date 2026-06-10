"""Entry: GUI with no args, CLI with subcommands."""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1:
        from .cli import main as cli_main

        cli_main()
    else:
        from .ui.main_window import run_app

        run_app()


if __name__ == "__main__":
    main()
