"""TCP upload pipeline: SourceFile -> CreateStudy -> WriteBatch -> Events -> Flush.

Batches are written in time-interleaved order (all channels for window t, then t+1),
matching EDF import's multi-channel time blocks so memtable flush can form the same
SSTable block shape.

FLOAT channels are uploaded as-is; compression / µV lossy quantize is done by the
EEGDB server (eegdb-codec), not the Python client.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

import numpy as np

from ..models import SourceFile, StudyAttrs
from ..transport.tcp_client import EEGDBTCPClient

ProgressCallback = Callable[[str, float], None]


def upload_source_file(
    client: EEGDBTCPClient,
    source: SourceFile,
    attrs: Optional[StudyAttrs] = None,
    batch_seconds: float = 10.0,
    on_progress: Optional[ProgressCallback] = None,
) -> str:
    attrs_dict = (attrs or StudyAttrs()).to_dict()
    channels = [ch.to_dict() for ch in source.channels]
    channel_data = {int(ch.channel_id): np.asarray(source.channel_data[int(ch.channel_id)]) for ch in source.channels}
    source_meta = {
        "original_name": os.path.basename(source.path),
        "format": source.format,
        "size_bytes": os.path.getsize(source.path) if source.path and os.path.isfile(source.path) else 0,
    }

    study_id = client.create_study(source.name, channels, attrs_dict, source_file=source_meta)
    if on_progress:
        on_progress("Study created", 0.05)

    if not channels:
        client.flush_study(study_id)
        return study_id

    # Use the first channel's rate for the shared time window (import-style).
    ref_rate = float(channels[0].get("sample_rate") or 1.0)
    batch_samples = max(1, int(round(ref_rate * batch_seconds)))
    totals = {int(ch["channel_id"]): len(channel_data[int(ch["channel_id"])]) for ch in channels}
    max_total = max(totals.values()) if totals else 0
    n_windows = (max_total + batch_samples - 1) // batch_samples if max_total else 0

    for w, start in enumerate(range(0, max_total, batch_samples)):
        for ch in channels:
            ch_id = int(ch["channel_id"])
            data = channel_data[ch_id]
            total = totals[ch_id]
            if start >= total:
                continue
            # Scale window by channel rate vs reference so mixed-rate files stay aligned in time.
            sample_rate = float(ch.get("sample_rate") or ref_rate)
            ch_batch = max(1, int(round(sample_rate / ref_rate * batch_samples)))
            ch_start = int(round(start * sample_rate / ref_rate))
            if ch_start >= total:
                continue
            end = min(ch_start + ch_batch, total)
            client.write_batch(study_id, ch_id, int(ch["data_type"]), ch_start, data[ch_start:end])
        if on_progress and n_windows:
            on_progress(f"Window {w + 1}/{n_windows}", 0.05 + 0.85 * (w + 1) / n_windows)

    if source.events:
        client.write_events(study_id, source.events)
        if on_progress:
            on_progress("Events written", 0.92)

    client.flush_study(study_id)
    if on_progress:
        on_progress("Flush complete", 1.0)
    return study_id
