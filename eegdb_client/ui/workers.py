"""Background worker thread shared by Fluent UI pages."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal


class Worker(QThread):
    progress = pyqtSignal(str, float)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            result = self._fn(*self._args, on_progress=self._emit, **self._kwargs)
            self.finished_ok.emit(str(result))
        except Exception as exc:
            self.failed.emit(str(exc))

    def _emit(self, msg: str, frac: float) -> None:
        self.progress.emit(msg, frac)
