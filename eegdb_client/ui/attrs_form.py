"""StudyAttrs editor with Fluent widgets and grouped fields."""

from __future__ import annotations

from PyQt6.QtWidgets import QFormLayout, QHBoxLayout, QHeaderView, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    LineEdit,
    PushButton,
    StrongBodyLabel,
    TableWidget,
)

from ..models import StudyAttrs

_STANDARD_FIELDS = (
    ("lab", "Lab"),
    ("pi", "Principal investigator"),
    ("device_type", "Device type"),
    ("device_serial", "Device serial"),
    ("sampling_rate", "Sampling rate"),
    ("paradigm", "Paradigm"),
    ("population", "Population"),
    ("condition", "Condition"),
    ("session", "Session"),
    ("ethics_approval", "Ethics approval"),
)


class StudyAttrsForm(CardWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("Study attributes"))
        layout.addWidget(BodyLabel("Optional metadata attached to the uploaded study."))

        form = QFormLayout()
        form.setSpacing(10)
        self._fields: dict[str, LineEdit] = {}
        for key, label in _STANDARD_FIELDS:
            edit = LineEdit()
            edit.setPlaceholderText(label)
            self._fields[key] = edit
            form.addRow(BodyLabel(label), edit)
        layout.addLayout(form)

        layout.addWidget(StrongBodyLabel("Custom fields"))
        layout.addWidget(self._build_custom_table())

    def _build_custom_table(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        self.custom_table = TableWidget()
        self.custom_table.setColumnCount(2)
        self.custom_table.setHorizontalHeaderLabels(["Key", "Value"])
        self.custom_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.custom_table.setBorderVisible(True)
        self.custom_table.setBorderRadius(8)
        self.custom_table.setMinimumHeight(140)
        v.addWidget(self.custom_table)

        row = QHBoxLayout()
        add_btn = PushButton("Add custom field")
        add_btn.clicked.connect(self._add_custom_row)
        remove_btn = PushButton("Remove selected")
        remove_btn.clicked.connect(self._remove_custom_rows)
        row.addWidget(add_btn)
        row.addWidget(remove_btn)
        row.addStretch()
        v.addLayout(row)
        return wrap

    def _add_custom_row(self, key: str = "", value: str = "") -> None:
        from PyQt6.QtWidgets import QTableWidgetItem

        row = self.custom_table.rowCount()
        self.custom_table.insertRow(row)
        self.custom_table.setItem(row, 0, QTableWidgetItem(key))
        self.custom_table.setItem(row, 1, QTableWidgetItem(value))

    def _remove_custom_rows(self) -> None:
        rows = sorted({i.row() for i in self.custom_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.custom_table.removeRow(row)

    def get_attrs(self) -> StudyAttrs:
        custom: dict[str, str] = {}
        for row in range(self.custom_table.rowCount()):
            key_item = self.custom_table.item(row, 0)
            val_item = self.custom_table.item(row, 1)
            key = (key_item.text() if key_item else "").strip()
            val = (val_item.text() if val_item else "").strip()
            if key:
                custom[key] = val

        kwargs = {name: edit.text().strip() for name, edit in self._fields.items()}
        kwargs["custom"] = custom
        return StudyAttrs(**kwargs)

    def set_attrs(self, attrs: StudyAttrs) -> None:
        for name, edit in self._fields.items():
            edit.setText(getattr(attrs, name, "") or "")
        self.custom_table.setRowCount(0)
        for key, value in (attrs.custom or {}).items():
            self._add_custom_row(key, value)

    def set_enabled(self, enabled: bool) -> None:
        for edit in self._fields.values():
            edit.setEnabled(enabled)
        self.custom_table.setEnabled(enabled)
