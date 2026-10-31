"""Research signal review, analysis preview, and manual quality annotation."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QFormLayout, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SpinBox,
    SubtitleLabel,
    TextEdit,
    InfoBar,
    InfoBarPosition,
)

from ...query_client import EEGDBQueryClient
from ..event_dialog import EventEditDialog
from ..quality_dialog import QualityReviewDialog
from ..workers import Worker

if TYPE_CHECKING:
    from ..main_window import MainWindow


class SignalPlot(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(260)
        self._x: list[float] = []
        self._y: list[float] = []
        self._marks: list[dict[str, Any]] = []

    def set_series(
        self,
        values: list[float],
        *,
        x_values: list[float] | None = None,
        marks: list[dict[str, Any]] | None = None,
    ) -> None:
        self._y = [float(value) for value in values]
        self._x = x_values or [float(index) for index in range(len(values))]
        self._marks = marks or []
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        area = self.rect().adjusted(42, 16, -16, -28)
        painter.setPen(QPen(self.palette().mid().color(), 1))
        painter.drawRect(area)
        if len(self._y) < 2:
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, "No preview loaded")
            return
        x_min, x_max = min(self._x), max(self._x)
        y_min, y_max = min(self._y), max(self._y)
        if x_max == x_min:
            x_max += 1
        if y_max == y_min:
            y_min, y_max = y_min - 1, y_max + 1

        for mark in self._marks:
            start = float(mark.get("start_index", x_min))
            end = float(mark.get("end_index", start))
            left = area.left() + (start - x_min) / (x_max - x_min) * area.width()
            right = area.left() + (end - x_min) / (x_max - x_min) * area.width()
            painter.fillRect(
                int(left), area.top(), max(2, int(right - left)), area.height(), QColor(220, 50, 47, 45)
            )

        path = QPainterPath()
        for index, (x_value, y_value) in enumerate(zip(self._x, self._y)):
            x = area.left() + (x_value - x_min) / (x_max - x_min) * area.width()
            y = area.bottom() - (y_value - y_min) / (y_max - y_min) * area.height()
            if index == 0:
                path.moveTo(QPointF(x, y))
            else:
                path.lineTo(QPointF(x, y))
        painter.setPen(QPen(QColor("#1677ff"), 1.2))
        painter.drawPath(path)
        painter.setPen(self.palette().text().color())
        painter.drawText(4, area.top() + 12, f"{y_max:.3g}")
        painter.drawText(4, area.bottom(), f"{y_min:.3g}")


class ReviewPage(QWidget):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self.setObjectName("reviewPage")
        self._window = window
        self._mode = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 24, 36, 24)
        root.addWidget(SubtitleLabel("Signal review & quality"))

        form = QFormLayout()
        self.study_edit = LineEdit()
        self.channel = SpinBox()
        self.channel.setRange(0, 65535)
        self.start = SpinBox()
        self.start.setRange(0, 2_000_000_000)
        self.end = SpinBox()
        self.end.setRange(1, 2_000_000_000)
        self.end.setValue(4096)
        self.event_code = LineEdit()
        self.event_code.setPlaceholderText("event code for ERP")
        form.addRow("Study ID", self.study_edit)
        form.addRow("Channel", self.channel)
        form.addRow("Start sample", self.start)
        form.addRow("End sample", self.end)
        form.addRow("ERP event code", self.event_code)
        root.addLayout(form)

        actions = QHBoxLayout()
        for text, callback in (
            ("Load review", self._load_review),
            ("Edit events", self._edit_events),
            ("PSD", self._load_psd),
            ("ERP", self._load_erp),
            ("Run quality scan", self._scan_quality),
            ("Review quality", self._review_quality),
        ):
            button = PrimaryPushButton(text) if text == "Load review" else PushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        actions.addStretch()
        root.addLayout(actions)

        self.plot = SignalPlot()
        root.addWidget(self.plot)
        self.summary = TextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(170)
        root.addWidget(self.summary)

        annotation = QHBoxLayout()
        self.issue = ComboBox()
        self.issue.addItems(
            ["unknown_artifact", "flatline", "spike", "bad_channel"]
        )
        self.severity = ComboBox()
        self.severity.addItems(["warning", "bad", "unusable", "info"])
        add_button = PushButton("Add manual annotation")
        add_button.clicked.connect(self._add_annotation)
        annotation.addWidget(BodyLabel("Issue"))
        annotation.addWidget(self.issue)
        annotation.addWidget(BodyLabel("Severity"))
        annotation.addWidget(self.severity)
        annotation.addWidget(add_button)
        annotation.addStretch()
        root.addLayout(annotation)

    def set_connected(self, connected: bool) -> None:
        self.setEnabled(connected and not self._window.is_busy())

    def _client(self) -> EEGDBQueryClient:
        tcp = self._window.require_client()
        if tcp is None:
            raise RuntimeError("connect to EEGDB first")
        base_url = tcp.http_url or f"https://{tcp.host}:8080"
        return EEGDBQueryClient(
            base_url,
            database=tcp.database,
            username=tcp.username,
            password=tcp.password,
            access_token=tcp.access_token,
            tls_verify=tcp.tls_verify,
        )

    def _study_id(self) -> str:
        study_id = self.study_edit.text().strip()
        if not study_id:
            raise ValueError("Study ID is required")
        return study_id

    def _run(self, mode: str, fn) -> None:
        self._mode = mode
        self._window.set_busy(True)

        def job(on_progress):
            return fn(self._client(), self._study_id())

        worker = Worker(job)
        worker.finished_value.connect(self._on_result)
        worker.failed.connect(self._on_failed)
        self._window.start_worker(worker)

    def _load_review(self) -> None:
        def query(client, study_id):
            signal = client.query_channel(
                study_id,
                self.channel.value(),
                idx_start=self.start.value(),
                idx_end=self.end.value(),
                physical=True,
            )
            return {
                "signal": signal,
                "events": client.query_events(study_id),
                "quality": client.query_quality(
                    study_id,
                    channel=self.channel.value(),
                    idx_start=self.start.value(),
                    idx_end=self.end.value(),
                ),
            }

        self._run("review", query)

    def _load_psd(self) -> None:
        self._run(
            "psd",
            lambda client, study_id: client.query_psd(
                study_id,
                channels=[self.channel.value()],
                idx_start=self.start.value(),
                idx_end=self.end.value(),
                physical=True,
            ),
        )

    def _edit_events(self) -> None:
        try:
            client = self._client()
            study_id = self._study_id()
            response = client.query_events(study_id)
            dialog = EventEditDialog(response.get("events") or [], self)
            if not dialog.exec():
                return
            events = dialog.events()
            client.replace_events(study_id, events)
        except Exception as exc:
            InfoBar.error(
                title="Event update failed",
                content=str(exc),
                parent=self._window,
                position=InfoBarPosition.TOP,
                duration=5000,
            )
            return
        InfoBar.success(
            title="Events updated",
            content=f"{len(events)} event(s) saved",
            parent=self._window,
            position=InfoBarPosition.TOP,
            duration=3000,
        )

    def _load_erp(self) -> None:
        self._run(
            "erp",
            lambda client, study_id: client.query_erp(
                study_id,
                channels=[self.channel.value()],
                code=self.event_code.text().strip(),
                pre_ms=200,
                post_ms=800,
                physical=True,
                reject_artifact=True,
            ),
        )

    def _scan_quality(self) -> None:
        self._run("quality", lambda client, study_id: client.scan_quality(study_id))

    def _review_quality(self) -> None:
        try:
            client, study_id = self._client(), self._study_id()
            response = client.query_quality(study_id)
            dialog = QualityReviewDialog(response.get("annotations") or [], self)
            if not dialog.exec():
                return
            for annotation in dialog.annotations():
                client.update_quality_annotation(study_id, int(annotation["id"]), annotation)
            for annotation_id in dialog.deleted_ids():
                client.delete_quality_annotation(study_id, annotation_id)
        except Exception as exc:
            InfoBar.error(title="Quality review failed", content=str(exc), parent=self._window, position=InfoBarPosition.TOP, duration=5000)
            return
        InfoBar.success(title="Quality review saved", content="Annotations and summaries updated", parent=self._window, position=InfoBarPosition.TOP, duration=3000)

    def _add_annotation(self) -> None:
        annotation = {
            "channel_id": self.channel.value(),
            "start_index": self.start.value(),
            "end_index": self.end.value(),
            "type": self.issue.currentText(),
            "severity": self.severity.currentText(),
            "source": "manual",
            "confidence": 1.0,
        }
        self._run(
            "quality",
            lambda client, study_id: client.add_quality_annotation(
                study_id, annotation
            ),
        )

    def _on_result(self, result: Any) -> None:
        self._window.set_busy(False)
        if self._mode == "review":
            signal = result["signal"]
            quality = result["quality"]
            marks = quality.get("annotations") or []
            start = self.start.value()
            samples = signal.get("samples") or []
            self.plot.set_series(
                samples,
                x_values=[float(start + index) for index in range(len(samples))],
                marks=marks,
            )
        elif self._mode == "psd":
            channel = (result.get("channels") or [{}])[0]
            psd = channel.get("psd") or {}
            self.plot.set_series(psd.get("power") or [], x_values=psd.get("freqs"))
        elif self._mode == "erp":
            channel = (result.get("channels") or [{}])[0]
            self.plot.set_series(
                channel.get("mean") or [], x_values=result.get("time_axis_ms")
            )
        self.summary.setPlainText(json.dumps(result, ensure_ascii=False, indent=2)[:12000])

    def _on_failed(self, message: str) -> None:
        self._window.set_busy(False)
        self.summary.setPlainText(message)
