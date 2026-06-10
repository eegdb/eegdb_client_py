"""Read FIF files via MNE into SourceFile."""

from __future__ import annotations

import os
from typing import List

import mne
import numpy as np

from ..models import DT_FLOAT32, ChannelDef, Event, SourceFile


def read_fif(path: str) -> SourceFile:
    raw = mne.io.read_raw_fif(path, preload=True, verbose=False)
    channels: List[ChannelDef] = []
    channel_data: dict[int, np.ndarray] = {}

    for i, name in enumerate(raw.ch_names):
        ch = raw.info["chs"][i]
        unit = _unit_name(ch.get("unit", mne.io.constants.FIFF.FIFF_UNIT_NONE))
        data = raw.get_data(picks=[i])[0]
        ch_def = ChannelDef(
            label=name,
            channel_id=i,
            sample_rate=float(raw.info["sfreq"]),
            data_type=DT_FLOAT32,
            type=raw.get_channel_types()[i],
            unit=unit,
            physical_min=float(np.min(data)),
            physical_max=float(np.max(data)),
        )
        channels.append(ch_def)
        channel_data[i] = data.astype(np.float32)

    events = _annotations_to_events(raw)
    return SourceFile(
        path=path,
        format="fif",
        name=os.path.splitext(os.path.basename(path))[0],
        channels=channels,
        events=events,
        patient_id=str(raw.info.get("subject_info") or ""),
        recording_id=raw.info.get("description") or "",
        start_time=raw.info.get("meas_date"),
        data_record_dur_sec=1.0,
        channel_data=channel_data,
    )


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
                code=str(desc),
                description=str(desc),
            )
        )
    return events
