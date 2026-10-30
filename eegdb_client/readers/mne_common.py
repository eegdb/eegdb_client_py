"""Shared helpers for MNE Raw -> SourceFile conversion."""

from __future__ import annotations

import os
from typing import List

import mne
import numpy as np

from ..models import DT_FLOAT32, ChannelDef, Event, SourceFile


def raw_to_source_file(raw: mne.io.BaseRaw, path: str, fmt: str) -> SourceFile:
    channels: List[ChannelDef] = []
    channel_lengths: dict[int, int] = {}

    for i, name in enumerate(raw.ch_names):
        ch = raw.info["chs"][i]
        unit = _unit_name(ch.get("unit", mne.io.constants.FIFF.FIFF_UNIT_NONE))
        physical_min, physical_max = _channel_extrema(raw, i)
        channels.append(
            ChannelDef(
                label=name,
                channel_id=i,
                sample_rate=float(raw.info["sfreq"]),
                data_type=DT_FLOAT32,
                type=raw.get_channel_types()[i],
                unit=unit,
                physical_min=physical_min,
                physical_max=physical_max,
            )
        )
        channel_lengths[i] = int(raw.n_times)

    return SourceFile(
        path=path,
        format=fmt,
        name=os.path.splitext(os.path.basename(path))[0],
        channels=channels,
        events=_annotations_to_events(raw),
        patient_id=str(raw.info.get("subject_info") or ""),
        recording_id=raw.info.get("description") or "",
        start_time=raw.info.get("meas_date"),
        data_record_dur_sec=1.0,
        channel_lengths=channel_lengths,
        channel_reader=lambda channel_id, start, stop: raw.get_data(
            picks=[channel_id], start=start, stop=stop
        )[0].astype(np.float32),
        close_callback=raw.close,
    )


def _channel_extrema(
    raw: mne.io.BaseRaw, channel_id: int, chunk_samples: int = 1_000_000
) -> tuple[float, float]:
    minimum, maximum = float("inf"), float("-inf")
    for start in range(0, int(raw.n_times), chunk_samples):
        values = raw.get_data(
            picks=[channel_id],
            start=start,
            stop=min(start + chunk_samples, raw.n_times),
        )[0]
        if values.size:
            minimum = min(minimum, float(np.min(values)))
            maximum = max(maximum, float(np.max(values)))
    if not np.isfinite(minimum) or not np.isfinite(maximum):
        return -1.0, 1.0
    if minimum == maximum:
        return minimum - 1.0, maximum + 1.0
    return minimum, maximum


def _unit_name(unit: int) -> str:
    mapping = {
        mne.io.constants.FIFF.FIFF_UNIT_V: "V",
        mne.io.constants.FIFF.FIFF_UNIT_T: "T",
        mne.io.constants.FIFF.FIFF_UNIT_NONE: "uV",
    }
    return mapping.get(unit, "uV")


def _annotations_to_events(raw: mne.io.BaseRaw) -> List[Event]:
    if raw.annotations is None or len(raw.annotations) == 0:
        return []
    events: List[Event] = []
    for onset, duration, desc in zip(raw.annotations.onset, raw.annotations.duration, raw.annotations.description):
        events.append(
            Event(
                onset=int(onset * 1_000_000),
                duration=int(duration * 1_000_000),
                channel_id=0xFFFF,
                type="marker",
                code=str(desc),
                description=str(desc),
                source="mne",
            )
        )
    return events
