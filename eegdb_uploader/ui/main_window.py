"""PyQt6 main window with upload and browse/download tabs."""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
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
from ..transport.http_client import EEGDBHTTPClient
from ..transport.tcp_client import EEGDBTCPClient
from ..upload.pipeline import upload_source_file
from .attrs_form import StudyAttrsForm


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
        self.setWindowTitle("EEGDB Uploader")
        self.resize(960, 780)
        self._worker: Optional[Worker] = None

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(self._build_conn_box())

        tabs = QTabWidget()
        tabs.addTab(self._build_upload_tab(), "Upload")
        tabs.addTab(self._build_browse_tab(), "Browse / Download")
        layout.addWidget(tabs)
        self.setCentralWidget(root)

    def _build_conn_box(self) -> QGroupBox:
        box = QGroupBox("Connection")
        form = QFormLayout(box)
        self.host_edit = QLineEdit("127.0.0.1")
        self.tcp_port_spin = QSpinBox()
        self.tcp_port_spin.setRange(1, 65535)
        self.tcp_port_spin.setValue(9090)
        self.http_port_spin = QSpinBox()
        self.http_port_spin.setRange(1, 65535)
        self.http_port_spin.setValue(8080)
        form.addRow("Host", self.host_edit)
        form.addRow("TCP port", self.tcp_port_spin)
        form.addRow("HTTP port", self.http_port_spin)
        return box

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

        self.upload_btn = QPushButton("Upload via TCP")
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

    def _tcp_client(self) -> EEGDBTCPClient:
        return EEGDBTCPClient(self.host_edit.text().strip(), self.tcp_port_spin.value())

    def _http_base(self) -> str:
        return f"http://{self.host_edit.text().strip()}:{self.http_port_spin.value()}"

    def _pick_upload_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select EDF/FIF", "", "EEG files (*.edf *.bdf *.fif)")
        if path:
            self.file_edit.setText(path)

    def _start_upload(self) -> None:
        path = self.file_edit.text().strip()
        if not path or not os.path.isfile(path):
            QMessageBox.warning(self, "Upload", "Select a valid file.")
            return
        self.upload_btn.setEnabled(False)
        self.upload_progress.setValue(0)
        attrs = self.attrs_form.get_attrs()

        def job(on_progress):
            ext = os.path.splitext(path)[1].lower()
            source = read_fif(path) if ext == ".fif" else read_edf(path)
            with self._tcp_client() as client:
                return upload_source_file(client, source, attrs, on_progress=on_progress)

        self._worker = Worker(job)
        self._worker.progress.connect(lambda m, f: (self.upload_status.setText(m), self.upload_progress.setValue(int(f * 100))))
        self._worker.finished_ok.connect(self._upload_done)
        self._worker.failed.connect(self._upload_failed)
        self._worker.start()

    def _upload_done(self, study_id: str) -> None:
        self.upload_btn.setEnabled(True)
        self.upload_status.setText(f"Uploaded: {study_id}")
        QMessageBox.information(self, "Upload", f"Study created: {study_id}")

    def _upload_failed(self, msg: str) -> None:
        self.upload_btn.setEnabled(True)
        QMessageBox.critical(self, "Upload failed", msg)

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
        try:
            EEGDBHTTPClient(self._http_base()).health()
            with self._tcp_client() as client:
                studies = client.list_studies()
        except Exception as exc:
            QMessageBox.critical(self, "Browse", str(exc))
            return
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
        try:
            with self._tcp_client() as client:
                studies = client.search_studies(attrs)
        except Exception as exc:
            QMessageBox.critical(self, "Search", str(exc))
            return
        self._fill_study_table(studies)

    def _start_download(self) -> None:
        rows = {idx.row() for idx in self.study_table.selectedIndexes()}
        if len(rows) != 1:
            QMessageBox.warning(self, "Download", "Select exactly one study.")
            return
        row = next(iter(rows))
        study_id = self.study_table.item(row, 0).text()
        fmt = self.fmt_combo.currentText()
        default_name = f"{study_id}.{fmt}"
        path, _ = QFileDialog.getSaveFileName(self, "Save as", default_name, f"*.{fmt}")
        if not path:
            return

        def job(on_progress):
            with self._tcp_client() as client:
                return download_study(client, study_id, path, fmt=fmt, on_progress=on_progress)

        self._worker = Worker(job)
        self._worker.progress.connect(lambda m, f: (self.dl_status.setText(m), self.dl_progress.setValue(int(f * 100))))
        self._worker.finished_ok.connect(lambda p: (self.dl_status.setText(f"Saved: {p}"), QMessageBox.information(self, "Download", f"Saved to {p}")))
        self._worker.failed.connect(lambda m: QMessageBox.critical(self, "Download failed", m))
        self._worker.start()


def run_app() -> None:
    import sys

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
