"""Launch EEGDB desktop uploader (PyInstaller-safe entry)."""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_path() -> None:
    if getattr(sys, "frozen", False):
        return
    client = Path(__file__).resolve().parent.parent
    if str(client) not in sys.path:
        sys.path.insert(0, str(client))


def main() -> None:
    _bootstrap_path()
    from eegdb_uploader.ui.main_window import run_app

    run_app()


if __name__ == "__main__":
    main()
