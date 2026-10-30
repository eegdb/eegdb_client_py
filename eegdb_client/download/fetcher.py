"""TCP download pipeline: query study -> ReadBatch / ReadCompressedBatch -> local file."""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Callable, Optional

import numpy as np

from ..codec_local import LocalCodec, parse_block_codec
from ..transport.tcp_client import EEGDBTCPClient
from .writers.edf_writer import write_edf_from_study
from .writers.fif_writer import write_fif_from_study
from .writers.npz_writer import write_npz_from_study

ProgressCallback = Callable[[str, float], None]
logger = logging.getLogger(__package__)


def download_study(
    client: EEGDBTCPClient,
    study_id: str,
    output_path: str,
    fmt: str = "edf",
    batch_size: int = 8192,
    on_progress: Optional[ProgressCallback] = None,
    *,
    local_decode: bool = False,
    block_codec: str = "balanced",
) -> str:
    """Download a study to a local file.

    When ``local_decode`` is True, each batch uses TCP ReadCompressedBatch and is
    decoded locally via eegdb-codec (requires the eegdb_codec package / shared lib).
    """
    logger.info(
        "download started study_id=%s format=%s local_decode=%s",
        study_id,
        fmt,
        local_decode,
    )
    study = client.get_study(study_id)
    channels = study.get("channels", [])
    if not channels:
        raise ValueError("study has no channels")

    codec = None
    codec_id = parse_block_codec(block_codec)
    if local_decode:
        codec = LocalCodec()

    total = int(study.get("num_samples") or 0)
    if total <= 0:
        start_idx = int(study.get("start_index") or 0)
        end_idx = int(study.get("end_index") or 0)
        total = max(0, end_idx - start_idx)

    with tempfile.TemporaryDirectory(prefix="eegdb-download-") as temp_dir:
        channel_data: dict[int, np.ndarray] = {}
        n = len(channels)
        for i, ch in enumerate(channels):
            ch_id = int(ch["channel_id"])
            data_type = int(ch.get("data_type", 0x01))
            ch_total = total
            if ch_total <= 0 and i == 0:
                ch_total = _probe_channel_length(client, study_id, ch_id, data_type)
            if ch_total <= 0:
                raise ValueError("cannot determine sample count for study")
            arr = _download_channel_to_disk(
                client,
                study_id,
                ch_id,
                data_type,
                ch_total,
                batch_size,
                os.path.join(temp_dir, f"channel-{ch_id}.bin"),
                local_decode=local_decode,
                block_codec=codec_id,
                codec=codec,
            )
            channel_data[ch_id] = arr
            if total <= 0 and i == 0:
                total = len(arr)
            if on_progress:
                on_progress(f"Downloaded {ch.get('label', ch_id)}", 0.9 * (i + 1) / n)

        events = client.read_events(study_id)
        ext = fmt.lower()
        if ext == "edf" and any(int(ch.get("data_type", 0)) == 0x02 for ch in channels):
            # EDF is 16-bit; INT24 studies must be written as BDF.
            ext = "bdf"
            root, _ = os.path.splitext(output_path)
            output_path = root + ".bdf"
        if ext == "npz":
            write_npz_from_study(output_path, study, channel_data, events)
        elif ext == "fif":
            if not output_path.endswith("_eeg.fif"):
                root, _ = os.path.splitext(output_path)
                output_path = root + "_eeg.fif"
            write_fif_from_study(output_path, study, channel_data, events)
        else:
            write_edf_from_study(output_path, study, channel_data, events, file_type=ext)

    if on_progress:
        on_progress("Saved " + os.path.basename(output_path), 1.0)
    logger.info("download completed study_id=%s output=%s", study_id, output_path)
    return output_path


def _download_channel_to_disk(
    client: EEGDBTCPClient,
    study_id: str,
    channel_id: int,
    data_type: int,
    total_samples: int,
    batch_size: int,
    temp_path: str,
    *,
    local_decode: bool,
    block_codec: int,
    codec: Optional[LocalCodec],
) -> np.ndarray:
    values = np.memmap(
        temp_path,
        dtype=client._numpy_dtype(data_type),
        mode="w+",
        shape=(total_samples,),
    )
    start = 0
    while start < total_samples:
        count = min(batch_size, total_samples - start)
        if local_decode:
            if codec is None:
                raise ValueError("local_decode requires a LocalCodec instance")
            _, got, algorithm, compressed = client.read_compressed_batch(
                study_id, channel_id, data_type, start, count, block_codec
            )
            batch = (
                codec.decode(data_type, algorithm, got, compressed)
                if got
                else np.empty(0)
            )
        else:
            _, batch = client.read_batch(study_id, channel_id, data_type, start, count)
            got = len(batch)
        if got == 0:
            break
        values[start : start + got] = batch
        start += got
    values.flush()
    return values[:start]


def _probe_channel_length(
    client: EEGDBTCPClient, study_id: str, channel_id: int, data_type: int
) -> int:
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
