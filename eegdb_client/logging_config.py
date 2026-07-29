"""Application-wide logging configuration."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from platformdirs import user_log_dir

_LOGGER_NAME = "eegdb_client"
_configured = False
_log_path: Optional[Path] = None


def default_log_path() -> Path:
    """Return the platform-appropriate EEGDB Client log path."""
    return Path(user_log_dir("EEGDBClient", ensure_exists=True)) / "eegdb-client.log"


def configure_logging(
    *,
    verbose: bool = False,
    log_file: str | os.PathLike[str] | None = None,
    console: bool = True,
) -> Path:
    """Configure rotating file logging and, optionally, console logging."""
    global _configured, _log_path

    path = Path(log_file).expanduser() if log_file else default_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if _configured:
        return _log_path or path

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s"
    )
    file_handler = RotatingFileHandler(
        path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    _configured = True
    _log_path = path
    logger.info("logging initialized: %s", path)
    return path


def install_exception_hook() -> None:
    """Log uncaught exceptions before delegating to Python's default hook."""
    original_hook = sys.excepthook

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            original_hook(exc_type, exc_value, exc_traceback)
            return
        logging.getLogger(_LOGGER_NAME).critical(
            "uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        original_hook(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception
