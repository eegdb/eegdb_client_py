"""TCP upload pipeline: SourceFile -> CreateStudy -> WriteBatch -> Events -> Flush.

Batches are written in time-interleaved order (all channels for window t, then t+1),
matching EDF import's multi-channel time blocks so memtable flush can form the same
SSTable block shape.

FLOAT channels are uploaded as-is; compression / µV lossy quantize is done by the
EEGDB server via eegdb-codec (pkg/codec), not the Python client.
Download may optionally use TCP ReadCompressedBatch + local eegdb_codec decode
(--local-decode).
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from ..models import SourceFile, StudyAttrs
from ..transport.tcp_client import EEGDBTCPClient

ProgressCallback = Callable[[str, float], None]
logger = logging.getLogger(__package__)


def upload_source_file(
    client: EEGDBTCPClient,
    source: SourceFile,
    attrs: Optional[StudyAttrs] = None,
    batch_seconds: float = 10.0,
    on_progress: Optional[ProgressCallback] = None,
) -> str:
    """Upload a source in bounded windows and release its backing reader."""
    try:
        return _upload_source_file(client, source, attrs, batch_seconds, on_progress)
    finally:
        source.close()


def _upload_source_file(
    client: EEGDBTCPClient,
    source: SourceFile,
    attrs: Optional[StudyAttrs],
    batch_seconds: float,
    on_progress: Optional[ProgressCallback],
) -> str:
    logger.info(
        "upload started file=%s format=%s channels=%s",
        os.path.basename(source.path),
        source.format,
        len(source.channels),
    )
    attrs_dict = (attrs or StudyAttrs()).to_dict()
    channels = [ch.to_dict() for ch in source.channels]
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
    totals = {int(ch["channel_id"]): source.channel_length(int(ch["channel_id"])) for ch in channels}
    max_total = max(
        (
            int(round(totals[int(ch["channel_id"])] * ref_rate / float(ch.get("sample_rate") or ref_rate)))
            for ch in channels
        ),
        default=0,
    )
    n_windows = (max_total + batch_samples - 1) // batch_samples if max_total else 0

    for w, start in enumerate(range(0, max_total, batch_samples)):
        for ch in channels:
            ch_id = int(ch["channel_id"])
            total = totals[ch_id]
            # Scale window by channel rate vs reference so mixed-rate files stay aligned in time.
            sample_rate = float(ch.get("sample_rate") or ref_rate)
            ch_batch = max(1, int(round(sample_rate / ref_rate * batch_samples)))
            ch_start = int(round(start * sample_rate / ref_rate))
            if ch_start >= total:
                continue
            end = min(ch_start + ch_batch, total)
            values = source.read_channel(ch_id, ch_start, end)
            client.write_batch(study_id, ch_id, int(ch["data_type"]), ch_start, values)
        if on_progress and n_windows:
            on_progress(f"Window {w + 1}/{n_windows}", 0.05 + 0.85 * (w + 1) / n_windows)

    if source.events:
        client.write_events_json(study_id, source.events)
        if on_progress:
            on_progress("Events written", 0.92)

    client.flush_study(study_id)
    if on_progress:
        on_progress("Flush complete", 1.0)
    logger.info("upload completed study_id=%s", study_id)
    return study_id
