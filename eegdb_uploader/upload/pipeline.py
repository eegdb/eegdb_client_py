"""TCP upload pipeline: SourceFile -> CreateStudy -> WriteBatch -> Events -> Flush."""

from __future__ import annotations

from typing import Callable, Optional

from ..models import SourceFile, StudyAttrs
from ..transport.tcp_client import EEGDBTCPClient

ProgressCallback = Callable[[str, float], None]


def upload_source_file(
    client: EEGDBTCPClient,
    source: SourceFile,
    attrs: Optional[StudyAttrs] = None,
    batch_seconds: float = 1.0,
    on_progress: Optional[ProgressCallback] = None,
) -> str:
    attrs_dict = (attrs or StudyAttrs()).to_dict()
    channels = [ch.to_dict() for ch in source.channels]

    study_id = client.create_study(source.name, channels, attrs_dict)
    if on_progress:
        on_progress("Study created", 0.05)

    n_channels = len(source.channels)
    for idx, ch in enumerate(source.channels):
        data = source.channel_data[ch.channel_id]
        batch_size = max(1, int(round(ch.sample_rate * batch_seconds)))
        total = len(data)
        start = 0
        while start < total:
            end = min(start + batch_size, total)
            client.write_batch(study_id, ch.channel_id, ch.data_type, start, data[start:end])
            start = end
            if on_progress:
                frac = 0.05 + 0.85 * ((idx + start / total) / n_channels)
                on_progress(f"Channel {ch.label}: {start}/{total}", frac)

    if source.events:
        client.write_events(study_id, source.events)
        if on_progress:
            on_progress("Events written", 0.92)

    client.flush_study(study_id)
    if on_progress:
        on_progress("Flush complete", 1.0)
    return study_id
