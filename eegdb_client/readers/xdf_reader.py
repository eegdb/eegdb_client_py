"""Read the primary EEG stream and marker streams from an XDF recording."""

from __future__ import annotations

import os
from typing import Any

import numpy as np

from ..models import DT_FLOAT32, ChannelDef, Event, SourceFile


def read_xdf(path: str) -> SourceFile:
    try:
        import pyxdf
    except ImportError as exc:
        raise RuntimeError("XDF support requires pyxdf: pip install pyxdf") from exc

    streams, _ = pyxdf.load_xdf(path)
    eeg = _select_eeg_stream(streams)
    samples = np.asarray(eeg.get("time_series"), dtype=np.float32)
    if samples.ndim == 1:
        samples = samples[:, None]
    if samples.ndim != 2 or samples.shape[0] == 0:
        raise ValueError("XDF EEG stream has no two-dimensional sample data")

    rate = float(_info_value(eeg, "nominal_srate", 0) or 0)
    if rate <= 0:
        stamps = np.asarray(eeg.get("time_stamps"), dtype=np.float64)
        if len(stamps) < 2:
            raise ValueError("cannot determine XDF EEG sample rate")
        rate = float(1.0 / np.median(np.diff(stamps)))

    labels = _channel_labels(eeg, samples.shape[1])
    channels = []
    channel_data = {}
    for channel_id, label in enumerate(labels):
        values = samples[:, channel_id]
        minimum, maximum = float(np.min(values)), float(np.max(values))
        if minimum == maximum:
            minimum, maximum = minimum - 1.0, maximum + 1.0
        channels.append(
            ChannelDef(
                label=label,
                channel_id=channel_id,
                sample_rate=rate,
                data_type=DT_FLOAT32,
                physical_min=minimum,
                physical_max=maximum,
            )
        )
        channel_data[channel_id] = values

    return SourceFile(
        path=path,
        format="xdf",
        name=os.path.splitext(os.path.basename(path))[0],
        channels=channels,
        events=_marker_events(streams, eeg),
        channel_data=channel_data,
    )


def _select_eeg_stream(streams: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        stream
        for stream in streams
        if str(_info_value(stream, "type", "")).strip().lower() == "eeg"
    ]
    if not candidates:
        candidates = [
            stream
            for stream in streams
            if float(_info_value(stream, "nominal_srate", 0) or 0) > 0
        ]
    if not candidates:
        raise ValueError("XDF file contains no sampled EEG stream")
    return max(
        candidates,
        key=lambda stream: len(stream.get("time_stamps", [])),
    )


def _info_value(stream: dict[str, Any], key: str, default: Any) -> Any:
    value = (stream.get("info") or {}).get(key, [default])
    if isinstance(value, list):
        return value[0] if value else default
    return value


def _channel_labels(stream: dict[str, Any], count: int) -> list[str]:
    try:
        entries = stream["info"]["desc"][0]["channels"][0]["channel"]
    except (KeyError, IndexError, TypeError):
        entries = []
    labels = []
    for index in range(count):
        try:
            label = entries[index].get("label", [f"CH{index}"])[0]
        except (IndexError, TypeError, AttributeError):
            label = f"CH{index}"
        labels.append(str(label))
    return labels


def _marker_events(
    streams: list[dict[str, Any]], eeg: dict[str, Any]
) -> list[Event]:
    eeg_stamps = np.asarray(eeg.get("time_stamps"), dtype=np.float64)
    origin = float(eeg_stamps[0]) if len(eeg_stamps) else 0.0
    events = []
    for stream in streams:
        stream_type = str(_info_value(stream, "type", "")).strip().lower()
        if stream_type not in {"markers", "marker"}:
            continue
        for stamp, value in zip(
            stream.get("time_stamps", []), stream.get("time_series", [])
        ):
            if isinstance(value, (list, tuple, np.ndarray)):
                value = value[0] if len(value) else ""
            code = str(value)
            events.append(
                Event(
                    onset=int(round((float(stamp) - origin) * 1_000_000)),
                    type="marker",
                    code=code,
                    description=code,
                    source="xdf",
                )
            )
    return events
