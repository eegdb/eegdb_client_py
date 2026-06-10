"""Launch EEGDB desktop client (GUI entry for development and PyInstaller)."""

from eegdb_client.ui.main_window import run_app


def main() -> None:
    run_app()


if __name__ == "__main__":
    main()
