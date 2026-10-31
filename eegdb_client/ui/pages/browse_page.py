"""Browse / search / download studies."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QSplitter,
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CheckBox,
    ComboBox,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    StrongBodyLabel,
    SubtitleLabel,
    TableWidget,
    TextEdit,
)

from ...download.fetcher import download_study
from ..study_dialog import StudyEditDialog
from ..workers import Worker

if TYPE_CHECKING:
    from ..main_window import MainWindow


class BrowsePage(QWidget):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self.setObjectName("browsePage")
        self._window = window
        self._studies: list[dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 24, 36, 24)
        root.setSpacing(12)

        root.addWidget(SubtitleLabel("Browse / Download"))
        root.addWidget(BodyLabel("Search studies on the server and download them locally."))

        search_row = QHBoxLayout()
        self.search_lab_edit = LineEdit()
        self.search_lab_edit.setPlaceholderText("lab (optional)")
        self.search_lab_edit.setClearButtonEnabled(True)
        self.search_paradigm_edit = LineEdit()
        self.search_paradigm_edit.setPlaceholderText("paradigm (optional)")
        self.search_paradigm_edit.setClearButtonEnabled(True)
        search_btn = PrimaryPushButton("Search")
        search_btn.clicked.connect(self._search_studies)
        refresh_btn = PushButton("List all")
        refresh_btn.clicked.connect(self._refresh_studies)
        search_row.addWidget(self.search_lab_edit)
        search_row.addWidget(self.search_paradigm_edit)
        search_row.addWidget(search_btn)
        search_row.addWidget(refresh_btn)
        root.addLayout(search_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.study_table = TableWidget()
        self.study_table.setColumnCount(5)
        self.study_table.setHorizontalHeaderLabels(["Study ID", "Name", "Channels", "Samples", "Lab"])
        self.study_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.study_table.setBorderVisible(True)
        self.study_table.setBorderRadius(8)
        self.study_table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self.study_table.setSelectionMode(TableWidget.SelectionMode.ExtendedSelection)
        self.study_table.itemSelectionChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.study_table)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.addWidget(StrongBodyLabel("Study details"))
        self.detail_view = TextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setPlaceholderText("Select a study to inspect attributes.")
        right_layout.addWidget(self.detail_view)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, stretch=1)

        dl_row = QHBoxLayout()
        dl_row.addWidget(BodyLabel("Format"))
        self.fmt_combo = ComboBox()
        self.fmt_combo.addItems(["edf", "bdf", "fif", "npz"])
        dl_row.addWidget(self.fmt_combo)

        self.local_decode_cb = CheckBox("Local decode (eegdb-codec)")
        self.codec_combo = ComboBox()
        self.codec_combo.addItems(["balanced", "fast", "smallest", "lz4", "zstd", "flac", "wavpack"])
        self.codec_combo.setEnabled(False)
        self.local_decode_cb.toggled.connect(self.codec_combo.setEnabled)
        dl_row.addWidget(self.local_decode_cb)
        dl_row.addWidget(BodyLabel("Codec"))
        dl_row.addWidget(self.codec_combo)

        self.download_btn = PrimaryPushButton("Download selected")
        self.download_btn.clicked.connect(self._start_download)
        self.edit_btn = PushButton("Edit metadata")
        self.edit_btn.clicked.connect(self._edit_study)
        self.delete_btn = PushButton("Delete study")
        self.delete_btn.clicked.connect(self._delete_study)
        dl_row.addWidget(self.edit_btn)
        dl_row.addWidget(self.delete_btn)
        dl_row.addWidget(self.download_btn)
        dl_row.addStretch()
        root.addLayout(dl_row)

        self.progress = ProgressBar()
        self.progress.setValue(0)
        self.status = BodyLabel("")
        root.addWidget(self.progress)
        root.addWidget(self.status)

        self.set_connected(False)

    def set_connected(self, connected: bool) -> None:
        busy = self._window.is_busy()
        enabled = connected and not busy
        self.study_table.setEnabled(enabled)
        self.download_btn.setEnabled(enabled)
        single_selected = len(self._selected_studies()) == 1
        self.edit_btn.setEnabled(enabled and single_selected)
        self.delete_btn.setEnabled(enabled and single_selected)
        self.search_lab_edit.setEnabled(not busy)
        self.search_paradigm_edit.setEnabled(not busy)

    def set_busy(self, busy: bool) -> None:
        self.set_connected(self._window.is_connected())

    def _fill_table(self, studies: list) -> None:
        self._studies = list(studies)
        self.study_table.setRowCount(len(studies))
        for row, s in enumerate(studies):
            attrs = s.get("attributes") or {}
            lab = attrs.get("lab", "") if isinstance(attrs, dict) else ""
            self.study_table.setItem(row, 0, QTableWidgetItem(s.get("study_id", "")))
            self.study_table.setItem(row, 1, QTableWidgetItem(s.get("name", "")))
            self.study_table.setItem(row, 2, QTableWidgetItem(str(s.get("num_channels", ""))))
            self.study_table.setItem(row, 3, QTableWidgetItem(str(s.get("num_samples", ""))))
            self.study_table.setItem(row, 4, QTableWidgetItem(str(lab)))
        self.detail_view.clear()

    def _selected_study(self) -> dict[str, Any] | None:
        studies = self._selected_studies()
        if len(studies) != 1:
            return None
        return studies[0]

    def _selected_studies(self) -> list[dict[str, Any]]:
        rows = sorted({idx.row() for idx in self.study_table.selectedIndexes()})
        return [self._studies[row] for row in rows if 0 <= row < len(self._studies)]

    def _on_selection_changed(self) -> None:
        study = self._selected_study()
        self.set_connected(self._window.is_connected())
        if study is None:
            count = len(self._selected_studies())
            self.detail_view.setPlainText(f"{count} studies selected" if count else "")
            return
        lines = [
            f"Study ID: {study.get('study_id', '')}",
            f"Name: {study.get('name', '')}",
            f"Channels: {study.get('num_channels', '')}",
            f"Samples: {study.get('num_samples', '')}",
            "",
            "Attributes:",
        ]
        attrs = study.get("attributes") or {}
        if isinstance(attrs, dict) and attrs:
            for key, value in attrs.items():
                lines.append(f"  {key}: {value}")
        else:
            lines.append("  (none)")
        self.detail_view.setPlainText("\n".join(lines))

    def _edit_study(self) -> None:
        study = self._selected_study()
        client = self._window.require_client()
        if study is None or client is None:
            return
        dialog = StudyEditDialog(study, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, attrs = dialog.values()
        try:
            client.update_study(study["study_id"], name=name, attrs=attrs)
        except Exception as exc:
            self._window.handle_tcp_failure("Update failed", str(exc))
            return
        self._refresh_studies()
        InfoBar.success(
            title="Study updated",
            content=study["study_id"],
            parent=self._window,
            position=InfoBarPosition.TOP,
            duration=3000,
        )

    def _delete_study(self) -> None:
        study = self._selected_study()
        client = self._window.require_client()
        if study is None or client is None:
            return
        study_id = study.get("study_id", "")
        answer = QMessageBox.question(
            self,
            "Delete study",
            f"Permanently delete {study_id} and all of its signal data?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            client.delete_study(study_id)
        except Exception as exc:
            self._window.handle_tcp_failure("Delete failed", str(exc))
            return
        self._refresh_studies()
        InfoBar.success(
            title="Study deleted",
            content=study_id,
            parent=self._window,
            position=InfoBarPosition.TOP,
            duration=3000,
        )

    def _run_list(self, title: str, fn) -> None:
        client = self._window.require_client()
        if client is None:
            return
        try:
            studies = fn(client)
        except Exception as exc:
            self._window.handle_tcp_failure(title, str(exc))
            return
        self._fill_table(studies)
        InfoBar.success(
            title=title,
            content=f"{len(studies)} study(ies)",
            parent=self._window,
            position=InfoBarPosition.TOP,
            duration=2000,
        )

    def _refresh_studies(self) -> None:
        self._run_list("Browse", lambda client: client.list_studies())

    def _search_studies(self) -> None:
        attrs = {}
        if self.search_lab_edit.text().strip():
            attrs["lab"] = self.search_lab_edit.text().strip()
        if self.search_paradigm_edit.text().strip():
            attrs["paradigm"] = self.search_paradigm_edit.text().strip()
        if not attrs:
            self._refresh_studies()
            return
        self._run_list("Search", lambda client: client.search_studies(attrs))

    def _start_download(self) -> None:
        studies = self._selected_studies()
        if not studies:
            InfoBar.warning(
                title="Download",
                content="Select one or more studies.",
                parent=self._window,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            return
        client = self._window.require_client()
        if client is None:
            return

        fmt = self.fmt_combo.currentText()
        if len(studies) == 1:
            study_id = studies[0].get("study_id", "")
            path, _ = QFileDialog.getSaveFileName(
                self, "Save as", f"{study_id}.{fmt}", f"*.{fmt}"
            )
            if not path:
                return
            targets = [(study_id, path)]
        else:
            directory = QFileDialog.getExistingDirectory(self, "Export selected studies")
            if not directory:
                return
            targets = [
                (
                    study.get("study_id", ""),
                    os.path.join(directory, f"{study.get('study_id', '')}.{fmt}"),
                )
                for study in studies
            ]

        self.progress.setValue(0)
        self.status.setText("Starting…")
        self._window.set_busy(True)

        local_decode = self.local_decode_cb.isChecked()
        block_codec = self.codec_combo.currentText()

        def job(on_progress):
            saved = []
            for index, (study_id, path) in enumerate(targets):

                def item_progress(message, fraction, index=index):
                    on_progress(
                        f"{study_id}: {message}",
                        (index + fraction) / len(targets),
                    )

                saved.append(
                    download_study(
                        client,
                        study_id,
                        path,
                        fmt=fmt,
                        on_progress=item_progress,
                        local_decode=local_decode,
                        block_codec=block_codec,
                    )
                )
            return saved[0] if len(saved) == 1 else f"{len(saved)} studies"

        worker = Worker(job)
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        self._window.start_worker(worker)

    def _on_progress(self, msg: str, frac: float) -> None:
        self.status.setText(msg)
        self.progress.setValue(int(frac * 100))

    def _on_done(self, saved_path: str) -> None:
        self.status.setText(f"Saved: {saved_path}")
        self._window.set_busy(False)
        InfoBar.success(
            title="Download complete",
            content=f"Saved to {saved_path}",
            parent=self._window,
            position=InfoBarPosition.TOP,
            duration=4000,
        )

    def _on_failed(self, msg: str) -> None:
        self.status.setText("")
        self._window.handle_tcp_failure("Download failed", msg)
