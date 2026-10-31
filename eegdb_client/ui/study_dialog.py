"""Study metadata editor dialog."""

from __future__ import annotations

from typing import Any, Mapping

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout
from qfluentwidgets import BodyLabel, LineEdit, SubtitleLabel

from ..models import StudyAttrs
from .attrs_form import StudyAttrsForm


class StudyEditDialog(QDialog):
    def __init__(self, study: Mapping[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit study")
        self.resize(650, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(SubtitleLabel("Edit study metadata"))
        layout.addWidget(BodyLabel(f"Study ID: {study.get('study_id', '')}"))

        self.name_edit = LineEdit()
        self.name_edit.setPlaceholderText("Study name")
        self.name_edit.setText(str(study.get("name", "")))
        layout.addWidget(self.name_edit)

        self.attrs_form = StudyAttrsForm()
        self.attrs_form.set_attrs(_study_attrs(study.get("attributes") or {}))
        layout.addWidget(self.attrs_form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, dict[str, Any]]:
        return self.name_edit.text().strip(), self.attrs_form.get_attrs().to_dict()


def _study_attrs(value: Mapping[str, Any]) -> StudyAttrs:
    known = {
        "lab",
        "pi",
        "device_type",
        "device_serial",
        "sampling_rate",
        "paradigm",
        "population",
        "condition",
        "session",
        "ethics_approval",
    }
    custom = {str(key): str(item) for key, item in (value.get("custom") or {}).items()}
    custom.update({str(key): str(item) for key, item in value.items() if key not in known | {"custom", "principal_investigator"}})
    return StudyAttrs(
        lab=str(value.get("lab", "")),
        pi=str(value.get("pi", value.get("principal_investigator", ""))),
        device_type=str(value.get("device_type", "")),
        device_serial=str(value.get("device_serial", "")),
        sampling_rate=str(value.get("sampling_rate", "")),
        paradigm=str(value.get("paradigm", "")),
        population=str(value.get("population", "")),
        condition=str(value.get("condition", "")),
        session=str(value.get("session", "")),
        ethics_approval=str(value.get("ethics_approval", "")),
        custom=custom,
    )
