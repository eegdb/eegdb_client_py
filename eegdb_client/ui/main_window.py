"""PyQt6 main window with upload and browse/download tabs."""

from __future__ import annotations

import os
from typing import Callable, Optional, TypeVar

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..download.fetcher import download_study
from ..readers.edf_reader import read_edf
from ..readers.fif_reader import read_fif
from ..transport.tcp_client import EEGDBTCPClient
from ..upload.pipeline import upload_source_file
from .attrs_form import StudyAttrsForm

T = TypeVar("T")


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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("EEGDB Client")
        self.resize(960, 780)
        self._worker: Optional[Worker] = None
        self._client: Optional[EEGDBTCPClient] = None

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(self._build_conn_box())

        tabs = QTabWidget()
        tabs.addTab(self._build_upload_tab(), "Upload")
        tabs.addTab(self._build_browse_tab(), "Browse / Download")
        layout.addWidget(tabs)
        self.setCentralWidget(root)
        self._update_conn_ui()

    def _build_conn_box(self) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("Host"))
        self.host_edit = QLineEdit("127.0.0.1")
        self.host_edit.setMaximumWidth(160)
        row.addWidget(self.host_edit)
        row.addWidget(QLabel("Port"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(8081)
        self.port_spin.setMaximumWidth(90)
        row.addWidget(self.port_spin)
        row.addWidget(QLabel("Token name"))
        self.token_name_edit = QLineEdit()
        self.token_name_edit.setPlaceholderText("optional")
        self.token_name_edit.setMaximumWidth(120)
        row.addWidget(self.token_name_edit)
        row.addWidget(QLabel("API token"))
        self.api_token_edit = QLineEdit()
        self.api_token_edit.setPlaceholderText("optional")
        self.api_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_token_edit.setMaximumWidth(200)
        row.addWidget(self.api_token_edit)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_connection)
        row.addWidget(self.connect_btn)
        self.conn_status = QLabel("Not connected")
        row.addWidget(self.conn_status)
        row.addStretch()
        return w

    def _build_upload_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        self.attrs_form = StudyAttrsForm()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.attrs_form)
        layout.addWidget(scroll)

        row = QHBoxLayout()
        self.file_edit = QLineEdit()
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._pick_upload_file)
        row.addWidget(self.file_edit)
        row.addWidget(browse_btn)
        layout.addLayout(row)

        self.upload_btn = QPushButton("Upload")
        self.upload_btn.clicked.connect(self._start_upload)
        layout.addWidget(self.upload_btn)

        self.upload_progress = QProgressBar()
        self.upload_status = QLabel("")
        layout.addWidget(self.upload_progress)
        layout.addWidget(self.upload_status)
        return w

    def _build_browse_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        search_row = QHBoxLayout()
        self.search_lab_edit = QLineEdit()
        self.search_lab_edit.setPlaceholderText("lab (optional)")
        self.search_paradigm_edit = QLineEdit()
        self.search_paradigm_edit.setPlaceholderText("paradigm (optional)")
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._search_studies)
        refresh_btn = QPushButton("List all")
        refresh_btn.clicked.connect(self._refresh_studies)
        search_row.addWidget(self.search_lab_edit)
        search_row.addWidget(self.search_paradigm_edit)
        search_row.addWidget(search_btn)
        search_row.addWidget(refresh_btn)
        layout.addLayout(search_row)

        self.study_table = QTableWidget(0, 5)
        self.study_table.setHorizontalHeaderLabels(["Study ID", "Name", "Channels", "Samples", "Lab"])
        self.study_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.study_table)

        dl_row = QHBoxLayout()
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(["edf", "bdf", "fif"])
        dl_btn = QPushButton("Download selected")
        dl_btn.clicked.connect(self._start_download)
        dl_row.addWidget(QLabel("Format"))
        dl_row.addWidget(self.fmt_combo)
        dl_row.addWidget(dl_btn)
        layout.addLayout(dl_row)

        self.dl_progress = QProgressBar()
        self.dl_status = QLabel("")
        layout.addWidget(self.dl_progress)
        layout.addWidget(self.dl_status)
        return w

    def _is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def _toggle_connection(self) -> None:
        if self._is_connected():
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        host = self.host_edit.text().strip()
        if not host:
            QMessageBox.warning(self, "Connect", "Enter a host.")
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
            QMessageBox.critical(self, "Connect failed", str(exc))
            return
        self._client = client
        self.conn_status.setText(f"Connected: {host}:{port}")
        self._update_conn_ui()

    def _disconnect(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
        self.conn_status.setText("Not connected")
        self._update_conn_ui()

    def _update_conn_ui(self) -> None:
        connected = self._is_connected()
        busy = self._worker is not None and self._worker.isRunning()
        self.host_edit.setEnabled(not connected)
        self.port_spin.setEnabled(not connected)
        self.token_name_edit.setEnabled(not connected)
        self.api_token_edit.setEnabled(not connected)
        self.connect_btn.setEnabled(not busy)
        self.connect_btn.setText("Disconnect" if connected else "Connect")
        self.upload_btn.setEnabled(connected and not busy)
        self.study_table.setEnabled(connected and not busy)

    def _require_client(self) -> EEGDBTCPClient:
        if not self._is_connected():
            raise RuntimeError("Not connected. Click Connect first.")
        return self._client  # type: ignore[return-value]

    def _run_tcp(self, title: str, fn: Callable[[EEGDBTCPClient], T]) -> Optional[T]:
        if not self._is_connected():
            QMessageBox.warning(self, title, "Connect to the server first.")
            return None
        try:
            return fn(self._require_client())
        except Exception as exc:
            self._on_tcp_error(title, exc)
            return None

    def _on_tcp_error(self, title: str, exc: Exception) -> None:
        if self._is_connected():
            self._disconnect()
        QMessageBox.critical(self, title, str(exc))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait()
        self._disconnect()
        super().closeEvent(event)

    def _pick_upload_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select EDF/FIF", "", "EEG files (*.edf *.bdf *.fif)")
        if path:
            self.file_edit.setText(path)

    def _start_upload(self) -> None:
        path = self.file_edit.text().strip()
        if not path or not os.path.isfile(path):
            QMessageBox.warning(self, "Upload", "Select a valid file.")
            return
        if not self._is_connected():
            QMessageBox.warning(self, "Upload", "Connect to the server first.")
            return
        self.upload_btn.setEnabled(False)
        self.connect_btn.setEnabled(False)
        self.upload_progress.setValue(0)
        attrs = self.attrs_form.get_attrs()
        client = self._require_client()

        def job(on_progress):
            ext = os.path.splitext(path)[1].lower()
            source = read_fif(path) if ext == ".fif" else read_edf(path)
            return upload_source_file(client, source, attrs, on_progress=on_progress)

        self._worker = Worker(job)
        self._worker.progress.connect(lambda m, f: (self.upload_status.setText(m), self.upload_progress.setValue(int(f * 100))))
        self._worker.finished_ok.connect(self._upload_done)
        self._worker.failed.connect(self._upload_failed)
        self._worker.start()

    def _upload_done(self, study_id: str) -> None:
        self.upload_status.setText(f"Uploaded: {study_id}")
        self._update_conn_ui()
        QMessageBox.information(self, "Upload", f"Study created: {study_id}")

    def _upload_failed(self, msg: str) -> None:
        self._on_tcp_error("Upload failed", RuntimeError(msg))
        self._update_conn_ui()

    def _fill_study_table(self, studies: list) -> None:
        self.study_table.setRowCount(len(studies))
        for row, s in enumerate(studies):
            attrs = s.get("attributes") or {}
            lab = attrs.get("lab", "") if isinstance(attrs, dict) else ""
            self.study_table.setItem(row, 0, QTableWidgetItem(s.get("study_id", "")))
            self.study_table.setItem(row, 1, QTableWidgetItem(s.get("name", "")))
            self.study_table.setItem(row, 2, QTableWidgetItem(str(s.get("num_channels", ""))))
            self.study_table.setItem(row, 3, QTableWidgetItem(str(s.get("num_samples", ""))))
            self.study_table.setItem(row, 4, QTableWidgetItem(str(lab)))

    def _refresh_studies(self) -> None:
        studies = self._run_tcp("Browse", lambda client: client.list_studies())
        if studies is not None:
            self._fill_study_table(studies)

    def _search_studies(self) -> None:
        attrs = {}
        if self.search_lab_edit.text().strip():
            attrs["lab"] = self.search_lab_edit.text().strip()
        if self.search_paradigm_edit.text().strip():
            attrs["paradigm"] = self.search_paradigm_edit.text().strip()
        if not attrs:
            self._refresh_studies()
            return
        studies = self._run_tcp("Search", lambda client: client.search_studies(attrs))
        if studies is not None:
            self._fill_study_table(studies)

    def _start_download(self) -> None:
        rows = {idx.row() for idx in self.study_table.selectedIndexes()}
        if len(rows) != 1:
            QMessageBox.warning(self, "Download", "Select exactly one study.")
            return
        if not self._is_connected():
            QMessageBox.warning(self, "Download", "Connect to the server first.")
            return
        row = next(iter(rows))
        study_id = self.study_table.item(row, 0).text()
        fmt = self.fmt_combo.currentText()
        default_name = f"{study_id}.{fmt}"
        path, _ = QFileDialog.getSaveFileName(self, "Save as", default_name, f"*.{fmt}")
        if not path:
            return
        client = self._require_client()
        self.connect_btn.setEnabled(False)
        self.upload_btn.setEnabled(False)
        self.study_table.setEnabled(False)

        def job(on_progress):
            return download_study(client, study_id, path, fmt=fmt, on_progress=on_progress)

        self._worker = Worker(job)
        self._worker.progress.connect(lambda m, f: (self.dl_status.setText(m), self.dl_progress.setValue(int(f * 100))))
        self._worker.finished_ok.connect(self._download_done)
        self._worker.failed.connect(self._download_failed)
        self._worker.start()

    def _download_done(self, saved_path: str) -> None:
        self.dl_status.setText(f"Saved: {saved_path}")
        self._update_conn_ui()
        QMessageBox.information(self, "Download", f"Saved to {saved_path}")

    def _download_failed(self, msg: str) -> None:
        self._on_tcp_error("Download failed", RuntimeError(msg))
        self._update_conn_ui()


def run_app() -> None:
    import sys

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
