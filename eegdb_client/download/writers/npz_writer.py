"""Write downloaded study arrays to a NumPy .npz archive."""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ...models import Event


def write_npz_from_study(
    output_path: str,
    study: Dict[str, Any],
    channel_data: Dict[int, np.ndarray],
    events: List[Event],
) -> None:
    channels = study.get("channels", [])
    if not channels:
        raise ValueError("no channels")

    arrays: Dict[str, Any] = {
        "study_id": np.asarray(study.get("study_id", "")),
        "name": np.asarray(study.get("name", "")),
        "channel_ids": np.asarray([int(ch["channel_id"]) for ch in channels], dtype=np.int32),
        "labels": np.asarray([str(ch.get("label", "")) for ch in channels]),
        "sample_rates": np.asarray([float(ch.get("sample_rate", 0.0)) for ch in channels], dtype=np.float64),
        "data_types": np.asarray([int(ch.get("data_type", 0)) for ch in channels], dtype=np.uint8),
    }

    for ch in channels:
        ch_id = int(ch["channel_id"])
        arrays[f"ch_{ch_id}"] = np.asarray(channel_data[ch_id])

    if events:
        arrays["event_onset"] = np.asarray([e.onset for e in events], dtype=np.int64)
        arrays["event_duration"] = np.asarray([e.duration for e in events], dtype=np.int64)
        arrays["event_channel_id"] = np.asarray([e.channel_id for e in events], dtype=np.uint16)
        arrays["event_code"] = np.asarray([e.code for e in events])
        arrays["event_description"] = np.asarray([e.description for e in events])

    np.savez_compressed(output_path, **arrays)
