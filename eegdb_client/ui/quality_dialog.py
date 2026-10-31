"""Quality annotation review table."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QMessageBox, QTableWidgetItem, QVBoxLayout
from qfluentwidgets import PushButton, SubtitleLabel, TableWidget

_COLUMNS = (
    ("id", "ID"), ("channel_id", "Channel"), ("start_index", "Start"),
    ("end_index", "End"), ("type", "Type"), ("severity", "Severity"),
    ("confidence", "Confidence"), ("source", "Source"), ("review_note", "Review note"),
)


class QualityReviewDialog(QDialog):
    def __init__(self, annotations: Iterable[Mapping[str, Any]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review quality annotations")
        self.resize(1050, 560)
        self._original = {int(item["id"]): dict(item) for item in annotations}
        self._deleted: set[int] = set()
        layout = QVBoxLayout(self)
        layout.addWidget(SubtitleLabel("Quality annotation review"))
        self.table = TableWidget()
        self.table.setColumnCount(len(_COLUMNS))
        self.table.setHorizontalHeaderLabels([label for _, label in _COLUMNS])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        for annotation in self._original.values():
            self._add(annotation)
        row = QHBoxLayout()
        remove = PushButton("Delete selected")
        remove.clicked.connect(self._remove)
        row.addWidget(remove)
        row.addStretch()
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_if_valid(self) -> None:
        try:
            self.annotations()
        except (KeyError, ValueError) as exc:
            QMessageBox.warning(self, "Invalid annotation", str(exc))
            return
        self.accept()

    def _add(self, value: Mapping[str, Any]) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, (key, _) in enumerate(_COLUMNS):
            item = QTableWidgetItem("" if value.get(key) is None else str(value.get(key, "")))
            if key in {"id", "source"}:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, column, item)

    def _remove(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self._deleted.add(int(self.table.item(row, 0).text()))
            self.table.removeRow(row)

    def deleted_ids(self) -> list[int]:
        return sorted(self._deleted)

    def annotations(self) -> list[dict[str, Any]]:
        result = []
        for row in range(self.table.rowCount()):
            values = {key: self.table.item(row, column).text().strip() for column, (key, _) in enumerate(_COLUMNS)}
            annotation_id = int(values["id"])
            annotation = dict(self._original[annotation_id])
            annotation.update({
                "channel_id": int(values["channel_id"]) if values["channel_id"] else None,
                "start_index": int(values["start_index"]), "end_index": int(values["end_index"]),
                "type": values["type"], "severity": values["severity"],
                "confidence": float(values["confidence"]), "source": values["source"],
                "review_note": values["review_note"],
            })
            if annotation["end_index"] <= annotation["start_index"]:
                raise ValueError(f"row {row + 1}: end must be greater than start")
            if annotation["severity"] not in {"info", "warning", "bad", "unusable"}:
                raise ValueError(f"row {row + 1}: invalid severity")
            if not 0 <= annotation["confidence"] <= 1:
                raise ValueError(f"row {row + 1}: confidence must be 0..1")
            result.append(annotation)
        return result
