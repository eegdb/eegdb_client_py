"""StudyAttrs editor with standard fields and custom key-value rows."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models import StudyAttrs


class StudyAttrsForm(QGroupBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Study attributes", parent)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._fields: dict[str, QLineEdit] = {}
        for key, label in (
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
        ):
            edit = QLineEdit()
            self._fields[key] = edit
            form.addRow(label, edit)
        layout.addLayout(form)

        layout.addWidget(self._build_custom_table())

    def _build_custom_table(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)

        self.custom_table = QTableWidget(0, 2)
        self.custom_table.setHorizontalHeaderLabels(["Key", "Value"])
        self.custom_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        v.addWidget(self.custom_table)

        row = QHBoxLayout()
        add_btn = QPushButton("Add custom field")
        add_btn.clicked.connect(self._add_custom_row)
        remove_btn = QPushButton("Remove selected")
        remove_btn.clicked.connect(self._remove_custom_rows)
        row.addWidget(add_btn)
        row.addWidget(remove_btn)
        row.addStretch()
        v.addLayout(row)
        return wrap

    def _add_custom_row(self, key: str = "", value: str = "") -> None:
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
