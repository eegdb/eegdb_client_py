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
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

from ..models import SourceFile, StudyAttrs
from ..transport.tcp_client import EEGDBTCPClient
from .checkpoint import (
    UploadCheckpoint,
    default_checkpoint_path,
    source_identity,
)

ProgressCallback = Callable[[str, float], None]
logger = logging.getLogger(__package__)


def upload_source_file(
    client: EEGDBTCPClient,
    source: SourceFile,
    attrs: Optional[StudyAttrs] = None,
    batch_seconds: float = 10.0,
    on_progress: Optional[ProgressCallback] = None,
    *,
    resume: bool = True,
    checkpoint_path: str | os.PathLike[str] | None = None,
) -> str:
    """Upload a source in bounded windows and release its backing reader."""
    try:
        return _upload_source_file(
            client,
            source,
            attrs,
            batch_seconds,
            on_progress,
            resume,
            checkpoint_path,
        )
    finally:
        source.close()


def _upload_source_file(
    client: EEGDBTCPClient,
    source: SourceFile,
    attrs: Optional[StudyAttrs],
    batch_seconds: float,
    on_progress: Optional[ProgressCallback],
    resume: bool,
    checkpoint_path: str | os.PathLike[str] | None,
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

    checkpoint_file = Path(checkpoint_path) if checkpoint_path else default_checkpoint_path(source.path, client)
    checkpoint: UploadCheckpoint | None = None
    if resume and checkpoint_file.is_file():
        checkpoint = UploadCheckpoint.load(checkpoint_file)
        checkpoint.validate(source.path, client)
        client.get_study(checkpoint.study_id)
        study_id = checkpoint.study_id
        if on_progress:
            on_progress(f"Resuming study {study_id}", 0.05)
    else:
        study_id = client.create_study(source.name, channels, attrs_dict, source_file=source_meta)
        if resume:
            identity = source_identity(source.path)
            checkpoint = UploadCheckpoint(
                **identity,
                host=str(getattr(client, "host", "")),
                port=int(getattr(client, "port", 0)),
                database=str(getattr(client, "database", "default")),
                study_id=study_id,
            )
            checkpoint.save(checkpoint_file)
        if on_progress:
            on_progress("Study created", 0.05)

    if not channels:
        client.flush_study(study_id)
        if resume:
            checkpoint_file.unlink(missing_ok=True)
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

    resume_start = checkpoint.next_window_start if checkpoint else 0
    for start in range(resume_start, max_total, batch_samples):
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
            completed = min(max_total, start + batch_samples)
            on_progress(
                f"Window {completed // batch_samples + (completed % batch_samples > 0)}/{n_windows}",
                0.05 + 0.85 * completed / max_total,
            )
        if resume:
            assert checkpoint is not None
            checkpoint.next_window_start = min(max_total, start + batch_samples)
            checkpoint.save(checkpoint_file)

    if source.events and (checkpoint is None or not checkpoint.events_complete):
        missing = source.events
        if checkpoint is not None:
            existing = client.read_events(study_id)
            missing = _missing_events(source.events, existing)
        if missing:
            client.write_events_json(study_id, missing)
        if checkpoint is not None:
            checkpoint.events_complete = True
            checkpoint.save(checkpoint_file)
        if on_progress:
            on_progress("Events written", 0.92)

    client.flush_study(study_id)
    if on_progress:
        on_progress("Flush complete", 1.0)
    if resume:
        checkpoint_file.unlink(missing_ok=True)
    logger.info("upload completed study_id=%s", study_id)
    return study_id


def _event_key(event) -> tuple:
    return (
        event.event_id,
        event.type,
        event.onset,
        event.duration,
        event.channel_id,
        event.code,
        event.description,
        event.trial_id,
        event.source,
        event.confidence,
        tuple(sorted(event.attributes.items())),
    )


def _missing_events(wanted, existing):
    remaining = Counter(_event_key(event) for event in existing)
    missing = []
    for event in wanted:
        key = _event_key(event)
        if remaining[key]:
            remaining[key] -= 1
        else:
            missing.append(event)
    return missing
