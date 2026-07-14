"""Connection settings page."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import QFormLayout, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PasswordLineEdit,
    PrimaryPushButton,
    PushButton,
    SpinBox,
    StrongBodyLabel,
    SubtitleLabel,
)

from ...transport.tcp_client import EEGDBTCPClient

if TYPE_CHECKING:
    from ..main_window import MainWindow


class ConnectPage(QWidget):
    connectionChanged = pyqtSignal(bool)

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self.setObjectName("connectPage")
        self._window = window
        self._settings = QSettings("eegdb", "eegdb_client")

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 24, 36, 24)
        root.setSpacing(16)

        root.addWidget(SubtitleLabel("Server connection"))
        root.addWidget(BodyLabel("Connect to an EEGDB TCP server before uploading or browsing studies."))

        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)

        self.host_edit = LineEdit()
        self.host_edit.setPlaceholderText("127.0.0.1")
        self.host_edit.setClearButtonEnabled(True)

        self.port_spin = SpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(8081)

        self.token_name_edit = LineEdit()
        self.token_name_edit.setPlaceholderText("optional")
        self.token_name_edit.setClearButtonEnabled(True)

        self.api_token_edit = PasswordLineEdit()
        self.api_token_edit.setPlaceholderText("optional — not saved to disk")

        form.addRow(BodyLabel("Host"), self.host_edit)
        form.addRow(BodyLabel("Port"), self.port_spin)
        form.addRow(BodyLabel("Token name"), self.token_name_edit)
        form.addRow(BodyLabel("API token"), self.api_token_edit)
        card_layout.addLayout(form)

        self.status_label = StrongBodyLabel("Not connected")
        card_layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        self.connect_btn = PrimaryPushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_connection)
        self.disconnect_btn = PushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self._disconnect)
        self.disconnect_btn.setEnabled(False)
        btn_row.addWidget(self.connect_btn)
        btn_row.addWidget(self.disconnect_btn)
        btn_row.addStretch()
        card_layout.addLayout(btn_row)

        root.addWidget(card)
        root.addStretch()

        self._load_settings()
        self._refresh_ui()

    def client(self) -> Optional[EEGDBTCPClient]:
        return self._window.client

    def is_connected(self) -> bool:
        return self._window.is_connected()

    def set_busy(self, busy: bool) -> None:
        connected = self.is_connected()
        self.connect_btn.setEnabled(not busy and not connected)
        self.disconnect_btn.setEnabled(not busy and connected)
        self.host_edit.setEnabled(not connected)
        self.port_spin.setEnabled(not connected)
        self.token_name_edit.setEnabled(not connected)
        self.api_token_edit.setEnabled(not connected)

    def _load_settings(self) -> None:
        self.host_edit.setText(self._settings.value("host", "127.0.0.1", type=str) or "127.0.0.1")
        self.port_spin.setValue(int(self._settings.value("port", 8081)))
        self.token_name_edit.setText(self._settings.value("token_name", "", type=str) or "")

    def _save_settings(self) -> None:
        self._settings.setValue("host", self.host_edit.text().strip())
        self._settings.setValue("port", self.port_spin.value())
        self._settings.setValue("token_name", self.token_name_edit.text().strip())

    def _toggle_connection(self) -> None:
        if self.is_connected():
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        host = self.host_edit.text().strip()
        if not host:
            InfoBar.warning(
                title="Connect",
                content="Enter a host.",
                parent=self._window,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            return
        port = self.port_spin.value()
        client = EEGDBTCPClient(
            host,
            port,
            token_name=self.token_name_edit.text().strip(),
            api_token=self.api_token_edit.text().strip(),
        )
        try:
            client.connect()
        except Exception as exc:
            InfoBar.error(
                title="Connect failed",
                content=str(exc),
                parent=self._window,
                position=InfoBarPosition.TOP,
                duration=5000,
            )
            return

        self._save_settings()
        self._window.set_client(client)
        self.status_label.setText(f"Connected: {host}:{port}")
        self._refresh_ui()
        self.connectionChanged.emit(True)
        InfoBar.success(
            title="Connected",
            content=f"{host}:{port}",
            parent=self._window,
            position=InfoBarPosition.TOP,
            duration=2500,
        )

    def _disconnect(self) -> None:
        self._window.set_client(None)
        self.status_label.setText("Not connected")
        self._refresh_ui()
        self.connectionChanged.emit(False)

    def on_forced_disconnect(self, reason: str = "") -> None:
        self.status_label.setText("Not connected")
        self._refresh_ui()
        self.connectionChanged.emit(False)
        if reason:
            InfoBar.error(
                title="Disconnected",
                content=reason,
                parent=self._window,
                position=InfoBarPosition.TOP,
                duration=5000,
            )

    def _refresh_ui(self) -> None:
        self.set_busy(self._window.is_busy())
