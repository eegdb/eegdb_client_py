"""Editable study event table used by the review workspace."""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
)
from qfluentwidgets import PushButton, SubtitleLabel, TableWidget


_COLUMNS = (
    ("event_id", "Event ID"),
    ("type", "Type"),
    ("onset_us", "Onset µs"),
    ("duration_us", "Duration µs"),
    ("channel_id", "Channel"),
    ("code", "Code"),
    ("description", "Description"),
    ("trial_id", "Trial ID"),
    ("source", "Source"),
    ("confidence", "Confidence"),
    ("attributes", "Attributes JSON"),
)


class EventEditDialog(QDialog):
    def __init__(self, events: Iterable[Mapping[str, Any]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit study events")
        self.resize(1180, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(SubtitleLabel("Study events"))

        self.table = TableWidget()
        self.table.setColumnCount(len(_COLUMNS))
        self.table.setHorizontalHeaderLabels([label for _, label in _COLUMNS])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(8)
        layout.addWidget(self.table)

        actions = QHBoxLayout()
        add_button = PushButton("Add event")
        add_button.clicked.connect(self._add_default)
        remove_button = PushButton("Remove selected")
        remove_button.clicked.connect(self._remove_selected)
        actions.addWidget(add_button)
        actions.addWidget(remove_button)
        actions.addStretch()
        layout.addLayout(actions)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        for event in events:
            self._add_event(event)

    def _accept_if_valid(self) -> None:
        try:
            self.events()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid event", str(exc))
            return
        self.accept()

    def _add_default(self) -> None:
        self._add_event(
            {
                "type": "marker",
                "onset_us": 0,
                "duration_us": 0,
                "channel_id": 0xFFFF,
                "code": "marker",
                "source": "manual",
                "confidence": 1.0,
            }
        )

    def _add_event(self, event: Mapping[str, Any]) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = dict(event)
        values["attributes"] = json.dumps(
            values.get("attributes") or {}, ensure_ascii=False, sort_keys=True
        )
        for column, (key, _) in enumerate(_COLUMNS):
            item = QTableWidgetItem(str(values.get(key, "")))
            if key == "event_id":
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, column, item)

    def _remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)

    def events(self) -> list[dict[str, Any]]:
        result = []
        for row in range(self.table.rowCount()):
            values = {
                key: (self.table.item(row, column).text().strip() if self.table.item(row, column) else "")
                for column, (key, _) in enumerate(_COLUMNS)
            }
            try:
                attributes = json.loads(values.pop("attributes") or "{}")
            except json.JSONDecodeError as exc:
                raise ValueError(f"row {row + 1}: invalid attributes JSON") from exc
            if not isinstance(attributes, dict):
                raise ValueError(f"row {row + 1}: attributes must be a JSON object")
            try:
                event = {
                    "type": values["type"],
                    "onset_us": int(values["onset_us"] or 0),
                    "duration_us": int(values["duration_us"] or 0),
                    "channel_id": int(values["channel_id"] or 0xFFFF),
                    "code": values["code"],
                    "description": values["description"],
                    "trial_id": values["trial_id"],
                    "source": values["source"],
                    "confidence": float(values["confidence"] or 0),
                    "attributes": {str(key): str(value) for key, value in attributes.items()},
                }
            except ValueError as exc:
                raise ValueError(f"row {row + 1}: invalid numeric value") from exc
            if event["type"] not in {"stimulus", "response", "artifact", "marker"}:
                raise ValueError(f"row {row + 1}: invalid event type")
            if not event["code"]:
                raise ValueError(f"row {row + 1}: code is required")
            if event["duration_us"] < 0:
                raise ValueError(f"row {row + 1}: duration must be non-negative")
            if event["type"] == "artifact" and event["duration_us"] == 0:
                raise ValueError(f"row {row + 1}: artifact duration is required")
            if not 0 <= event["channel_id"] <= 0xFFFF:
                raise ValueError(f"row {row + 1}: channel must be 0..65535")
            if not 0 <= event["confidence"] <= 1:
                raise ValueError(f"row {row + 1}: confidence must be 0..1")
            if values["event_id"]:
                event["event_id"] = values["event_id"]
            result.append(event)
        return result
