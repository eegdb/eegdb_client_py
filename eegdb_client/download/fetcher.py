"""TCP download pipeline: query study -> ReadBatch -> local file."""

from __future__ import annotations

import os
from typing import Callable, Optional

import numpy as np

from ..transport.tcp_client import EEGDBTCPClient
from .writers.edf_writer import write_edf_from_study
from .writers.fif_writer import write_fif_from_study

ProgressCallback = Callable[[str, float], None]


def download_study(
    client: EEGDBTCPClient,
    study_id: str,
    output_path: str,
    fmt: str = "edf",
    batch_size: int = 8192,
    on_progress: Optional[ProgressCallback] = None,
) -> str:
    study = client.get_study(study_id)
    channels = study.get("channels", [])
    if not channels:
        raise ValueError("study has no channels")

    channel_data: dict[int, np.ndarray] = {}
    n = len(channels)

    total = int(study.get("num_samples") or 0)
    if total <= 0:
        start_idx = int(study.get("start_index") or 0)
        end_idx = int(study.get("end_index") or 0)
        total = max(0, end_idx - start_idx)

    for i, ch in enumerate(channels):
        ch_id = ch["channel_id"]
        data_type = ch.get("data_type", 0x01)
        ch_total = total
        if ch_total <= 0 and i == 0:
            ch_total = _probe_channel_length(client, study_id, ch_id, data_type)
        if ch_total <= 0:
            raise ValueError("cannot determine sample count for study")
        arr = client.read_channel_all(study_id, ch_id, data_type, ch_total, batch_size)
        channel_data[ch_id] = arr
        if total <= 0 and i == 0:
            total = len(arr)
        if on_progress:
            on_progress(f"Downloaded {ch.get('label', ch_id)}", (i + 1) / n)

    events = client.read_events(study_id)
    ext = fmt.lower()
    if ext == "edf" and any(int(ch.get("data_type", 0)) == 0x02 for ch in channels):
        # EDF is 16-bit; INT24 studies must be written as BDF.
        ext = "bdf"
        root, _ = os.path.splitext(output_path)
        output_path = root + ".bdf"
    if ext == "fif":
        write_fif_from_study(output_path, study, channel_data, events)
    else:
        write_edf_from_study(output_path, study, channel_data, events, file_type=ext)

    if on_progress:
        on_progress("Saved " + os.path.basename(output_path), 1.0)
    return output_path


def _probe_channel_length(client: EEGDBTCPClient, study_id: str, channel_id: int, data_type: int) -> int:
    """Binary search upper bound when study metadata lacks sample count."""
    lo, hi = 0, 1
    while True:
        try:
            _, arr = client.read_batch(study_id, channel_id, data_type, hi - 1, 1)
            if len(arr) == 0:
                break
            lo = hi
            hi *= 2
            if hi > 10_000_000:
                raise ValueError("sample count exceeds probe limit")
        except Exception:
            break
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        try:
            _, arr = client.read_batch(study_id, channel_id, data_type, mid, 1)
            if len(arr) > 0:
                lo = mid + 1
            else:
                hi = mid
        except Exception:
            hi = mid
    return lo
