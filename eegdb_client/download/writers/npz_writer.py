"""NPZ writer for downloaded EEGDB studies."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import numpy as np

from ...models import Event


def write_npz_from_study(
    output_path: str,
    study: Dict[str, Any],
    channel_data: Dict[int, np.ndarray],
    events: List[Event],
) -> None:
    arrays: Dict[str, np.ndarray] = {}
    labels = []
    channel_ids = []
    sample_rates = []
    for ch in study.get("channels", []):
        ch_id = int(ch["channel_id"])
        if ch_id not in channel_data:
            continue
        arrays[f"ch_{ch_id}"] = np.asarray(channel_data[ch_id])
        labels.append(ch.get("label", str(ch_id)))
        channel_ids.append(ch_id)
        sample_rates.append(float(ch.get("sample_rate", 0.0)))

    metadata = {
        "study_id": study.get("study_id"),
        "name": study.get("name"),
        "channels": study.get("channels", []),
        "attributes": study.get("attributes", {}),
        "events": [e.__dict__ for e in events],
    }
    arrays["channel_ids"] = np.asarray(channel_ids, dtype=np.uint16)
    arrays["channel_labels"] = np.asarray(labels)
    arrays["sample_rates"] = np.asarray(sample_rates, dtype=np.float64)
    arrays["metadata_json"] = np.asarray(json.dumps(metadata, ensure_ascii=False))
    np.savez_compressed(output_path, **arrays)
