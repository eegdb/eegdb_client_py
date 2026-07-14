"""Upload page: pick file, edit attributes, upload."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    StrongBodyLabel,
    SubtitleLabel,
)

from ...readers import load_source_file
from ...upload.pipeline import upload_source_file
from ..attrs_form import StudyAttrsForm
from ..workers import Worker

if TYPE_CHECKING:
    from ..main_window import MainWindow


class UploadPage(QWidget):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self.setObjectName("uploadPage")
        self._window = window

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 24, 36, 24)
        root.setSpacing(16)

        root.addWidget(SubtitleLabel("Upload"))
        root.addWidget(BodyLabel("Select an EEG file, fill study attributes, then upload over TCP."))

        file_card = CardWidget()
        file_layout = QVBoxLayout(file_card)
        file_layout.setContentsMargins(16, 16, 16, 16)
        file_layout.setSpacing(10)
        file_layout.addWidget(StrongBodyLabel("Source file"))
        self.file_summary = BodyLabel("No file selected")
        file_layout.addWidget(self.file_summary)

        file_row = QHBoxLayout()
        self.file_edit = LineEdit()
        self.file_edit.setPlaceholderText("Path to .edf / .bdf / .fif / .cdt …")
        self.file_edit.setClearButtonEnabled(True)
        self.file_edit.textChanged.connect(self._on_file_path_changed)
        browse_btn = PushButton("Browse…")
        browse_btn.clicked.connect(self._pick_file)
        file_row.addWidget(self.file_edit, stretch=1)
        file_row.addWidget(browse_btn)
        file_layout.addLayout(file_row)
        root.addWidget(file_card)

        self.attrs_form = StudyAttrsForm()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.attrs_form)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        root.addWidget(scroll, stretch=1)

        action_row = QHBoxLayout()
        self.upload_btn = PrimaryPushButton("Upload")
        self.upload_btn.clicked.connect(self._start_upload)
        action_row.addWidget(self.upload_btn)
        action_row.addStretch()
        root.addLayout(action_row)

        self.progress = ProgressBar()
        self.progress.setValue(0)
        self.status = BodyLabel("")
        root.addWidget(self.progress)
        root.addWidget(self.status)

        self.set_connected(False)

    def set_connected(self, connected: bool) -> None:
        busy = self._window.is_busy()
        enabled = connected and not busy
        self.upload_btn.setEnabled(enabled)
        self.file_edit.setEnabled(not busy)
        self.attrs_form.set_enabled(not busy)

    def set_busy(self, busy: bool) -> None:
        self.set_connected(self._window.is_connected())

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select EEG file",
            "",
            "EEG files (*.edf *.bdf *.fif *.cdt *.ceo *.dap *.rs3 *.rs4)",
        )
        if path:
            self.file_edit.setText(path)

    def _on_file_path_changed(self, path: str) -> None:
        path = path.strip()
        if not path:
            self.file_summary.setText("No file selected")
            return
        if not os.path.isfile(path):
            self.file_summary.setText("File not found")
            return
        name = os.path.basename(path)
        size_mb = os.path.getsize(path) / (1024 * 1024)
        ext = os.path.splitext(name)[1].lstrip(".").upper() or "?"
        self.file_summary.setText(f"{name}  ·  {ext}  ·  {size_mb:.2f} MB")

    def _start_upload(self) -> None:
        path = self.file_edit.text().strip()
        if not path or not os.path.isfile(path):
            InfoBar.warning(
                title="Upload",
                content="Select a valid file.",
                parent=self._window,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            return
        client = self._window.require_client()
        if client is None:
            return

        attrs = self.attrs_form.get_attrs()
        self.progress.setValue(0)
        self.status.setText("Starting…")
        self._window.set_busy(True)

        def job(on_progress):
            source = load_source_file(path)
            return upload_source_file(client, source, attrs, on_progress=on_progress)

        worker = Worker(job)
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        self._window.start_worker(worker)

    def _on_progress(self, msg: str, frac: float) -> None:
        self.status.setText(msg)
        self.progress.setValue(int(frac * 100))

    def _on_done(self, study_id: str) -> None:
        self.status.setText(f"Uploaded: {study_id}")
        self._window.set_busy(False)
        InfoBar.success(
            title="Upload complete",
            content=f"Study created: {study_id}",
            parent=self._window,
            position=InfoBarPosition.TOP,
            duration=4000,
        )

    def _on_failed(self, msg: str) -> None:
        self.status.setText("")
        self._window.handle_tcp_failure("Upload failed", msg)
