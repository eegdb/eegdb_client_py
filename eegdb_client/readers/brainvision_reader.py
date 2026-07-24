"""Read BrainVision files via MNE into SourceFile."""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

from ..models import DT_FLOAT32, ChannelDef, Event, SourceFile


def read_brainvision(path: str) -> SourceFile:
    import mne
    import numpy as np

    raw = mne.io.read_raw_brainvision(path, preload=True, verbose=False)
    channels: List[ChannelDef] = []
    channel_data: dict[int, np.ndarray] = {}
    channel_types = raw.get_channel_types()

    for i, name in enumerate(raw.ch_names):
        data = raw.get_data(picks=[i])[0].astype(np.float32)
        unit = _brainvision_unit(raw, i)
        ch_def = ChannelDef(
            label=name,
            channel_id=i,
            sample_rate=float(raw.info["sfreq"]),
            data_type=DT_FLOAT32,
            type=channel_types[i],
            unit=unit,
            physical_min=float(np.min(data)) if data.size else 0.0,
            physical_max=float(np.max(data)) if data.size else 0.0,
        )
        channels.append(ch_def)
        channel_data[i] = data

    return SourceFile(
        path=path,
        format="brainvision",
        name=os.path.splitext(os.path.basename(path))[0],
        channels=channels,
        events=_annotations_to_events(raw),
        patient_id="",
        recording_id=raw.info.get("description") or "",
        start_time=_meas_date(raw.info.get("meas_date")),
        data_record_dur_sec=1.0,
        channel_data=channel_data,
    )


def _annotations_to_events(raw: Any) -> List[Event]:
    if raw.annotations is None or len(raw.annotations) == 0:
        return []
    events: List[Event] = []
    trial_id = ""
    trial_index = 0
    for onset, duration, desc in zip(raw.annotations.onset, raw.annotations.duration, raw.annotations.description):
        event_type, code, attrs = normalize_brainvision_marker(str(desc))
        duration_us = int(float(duration) * 1_000_000)
        if event_type == "artifact" and duration_us <= 0:
            duration_us = 1
        if event_type == "marker" and code in {"trial_start", "new_segment"}:
            trial_index += 1
            trial_id = f"trial-{trial_index:06d}"
        elif event_type == "stimulus" and not trial_id:
            trial_index += 1
            trial_id = f"trial-{trial_index:06d}"
        events.append(
            Event(
                type=event_type,
                onset=int(float(onset) * 1_000_000),
                duration=duration_us,
                channel_id=0xFFFF,
                code=code,
                description=str(desc),
                trial_id=trial_id,
                source="brainvision",
                attributes=attrs,
            )
        )
    return events


def normalize_brainvision_marker(description: str) -> Tuple[str, str, Dict[str, str]]:
    text = description.strip()
    kind, code = _split_marker(text)
    kind_l = kind.lower()
    attrs = {
        "brainvision_marker": text,
        "brainvision_kind": kind,
    }
    if code:
        attrs["brainvision_code"] = code

    if kind_l.startswith("stimulus") or kind_l == "s":
        return "stimulus", _clean_code(code or text), attrs
    if kind_l.startswith("response") or kind_l == "r":
        return "response", _clean_code(code or text), attrs
    if kind_l in {"bad interval", "artifact", "bad", "boundary"} or "artifact" in kind_l:
        return "artifact", _clean_code(code or "artifact"), attrs
    if kind_l in {"new segment", "sync status"}:
        return "marker", _clean_code(kind), attrs
    return "marker", _clean_code(code or text), attrs


def _split_marker(text: str) -> Tuple[str, str]:
    if "/" in text:
        kind, code = text.split("/", 1)
        return kind.strip(), code.strip()
    match = re.match(r"^([A-Za-z]+)\s+(.+)$", text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return text, ""


def _clean_code(value: str) -> str:
    value = value.strip().replace(" ", "_")
    value = re.sub(r"[^0-9A-Za-z_.:-]+", "_", value)
    value = re.sub(r"_+", "_", value)
    value = value.strip("_")
    return value or "marker"


def _brainvision_unit(raw: Any, index: int) -> str:
    try:
        unit_mul = raw.info["chs"][index].get("unit_mul")
        if unit_mul == 0:
            return "V"
    except Exception:
        pass
    return "uV"


def _meas_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return None
