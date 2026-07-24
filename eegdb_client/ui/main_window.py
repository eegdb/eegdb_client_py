"""Fluent desktop main window: Connect / Upload / Browse."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication
from qfluentwidgets import (
    FluentIcon as FIF,
    FluentWindow,
    NavigationItemPosition,
    Theme,
    setTheme,
)

from ..transport.tcp_client import EEGDBTCPClient
from .pages import BrowsePage, ConnectPage, UploadPage
from .workers import Worker


class MainWindow(FluentWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("EEGDB Client")
        self.resize(1100, 780)

        self._client: Optional[EEGDBTCPClient] = None
        self._worker: Optional[Worker] = None
        self._busy = False

        self.connect_page = ConnectPage(self)
        self.upload_page = UploadPage(self)
        self.browse_page = BrowsePage(self)

        self.addSubInterface(self.connect_page, FIF.CONNECT, "Connect")
        self.addSubInterface(self.upload_page, FIF.UP, "Upload")
        self.addSubInterface(self.browse_page, FIF.SEARCH, "Browse")

        self.navigationInterface.addItem(
            routeKey="theme",
            icon=FIF.CONSTRACT,
            text="Theme",
            onClick=self._toggle_theme,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )

        self.connect_page.connectionChanged.connect(self._on_connection_changed)
        self._theme_dark = False
        setTheme(Theme.AUTO)

    @property
    def client(self) -> Optional[EEGDBTCPClient]:
        return self._client

    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def is_busy(self) -> bool:
        return self._busy or (self._worker is not None and self._worker.isRunning())

    def set_client(self, client: Optional[EEGDBTCPClient]) -> None:
        if self._client is not None and client is not self._client:
            self._client.close()
        self._client = client
        self._sync_pages()

    def require_client(self) -> Optional[EEGDBTCPClient]:
        if not self.is_connected():
            from qfluentwidgets import InfoBar, InfoBarPosition

            InfoBar.warning(
                title="Not connected",
                content="Connect to the server first.",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            return None
        return self._client

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._sync_pages()

    def start_worker(self, worker: Worker) -> None:
        self._worker = worker
        worker.start()

    def handle_tcp_failure(self, title: str, message: str) -> None:
        if self.is_connected():
            self.set_client(None)
            self.connect_page.on_forced_disconnect(f"{title}: {message}")
        else:
            from qfluentwidgets import InfoBar, InfoBarPosition

            InfoBar.error(
                title=title,
                content=message,
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000,
            )
        self.set_busy(False)

    def _on_connection_changed(self, connected: bool) -> None:
        self._sync_pages()
        if connected:
            self.switchTo(self.browse_page)

    def _sync_pages(self) -> None:
        connected = self.is_connected()
        busy = self.is_busy()
        self.connect_page.set_busy(busy)
        self.upload_page.set_connected(connected)
        self.browse_page.set_connected(connected)

    def _toggle_theme(self) -> None:
        self._theme_dark = not self._theme_dark
        setTheme(Theme.DARK if self._theme_dark else Theme.LIGHT)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait()
        self.set_client(None)
        super().closeEvent(event)


def run_app() -> None:
    import sys

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings)
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
