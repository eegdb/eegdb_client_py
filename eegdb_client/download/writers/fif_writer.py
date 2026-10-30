"""Write downloaded study data to FIF via MNE."""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List

import mne
import numpy as np

from ...models import Event


def write_fif_from_study(
    output_path: str,
    study: Dict[str, Any],
    channel_data: Dict[int, np.ndarray],
    events: List[Event],
) -> None:
    channels = study.get("channels", [])
    if not channels:
        raise ValueError("no channels")

    sfreq = float(channels[0].get("sample_rate", 256.0))
    ch_names = [str(ch.get("label", f"CH{ch['channel_id']}")) for ch in channels]
    if not output_path.endswith("_eeg.fif"):
        base, _ = os.path.splitext(output_path)
        output_path = f"{base}_eeg.fif"

    sample_count = min(len(channel_data[ch["channel_id"]]) for ch in channels)
    with tempfile.TemporaryDirectory(prefix="eegdb-fif-") as temp_dir:
        data = np.memmap(
            os.path.join(temp_dir, "channels.bin"),
            dtype=np.float64,
            mode="w+",
            shape=(len(channels), sample_count),
        )
        for i, ch in enumerate(channels):
            data[i] = channel_data[ch["channel_id"]][:sample_count]
        data.flush()

        info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
        raw = mne.io.RawArray(data, info, copy=None)
        if events:
            onsets = [e.onset / 1_000_000.0 for e in events]
            durations = [e.duration / 1_000_000.0 for e in events]
            descriptions = [e.description or e.code for e in events]
            raw.set_annotations(mne.Annotations(onsets, durations, descriptions))
        raw.save(output_path, overwrite=True)
