"""Capture a bounded segment from a Lab Streaming Layer EEG stream."""

from __future__ import annotations

import time

import numpy as np

from ..models import DT_FLOAT32, ChannelDef, SourceFile


def record_lsl(
    duration_seconds: float,
    *,
    stream_name: str = "",
    stream_type: str = "EEG",
    resolve_timeout: float = 5.0,
) -> SourceFile:
    if duration_seconds <= 0:
        raise ValueError("LSL capture duration must be positive")
    try:
        import pylsl
    except ImportError as exc:
        raise RuntimeError("LSL support requires pylsl: pip install pylsl") from exc

    prop, value = ("name", stream_name) if stream_name else ("type", stream_type)
    streams = pylsl.resolve_byprop(prop, value, minimum=1, timeout=resolve_timeout)
    if not streams:
        raise TimeoutError(f"no LSL stream found with {prop}={value!r}")
    info = streams[0]
    inlet = pylsl.StreamInlet(info)
    chunks = []
    timestamps = []
    deadline = time.monotonic() + duration_seconds
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        samples, stamps = inlet.pull_chunk(
            timeout=max(0.0, min(0.5, remaining)), max_samples=1024
        )
        if samples:
            chunks.append(np.asarray(samples, dtype=np.float32))
            timestamps.extend(stamps)
    if not chunks:
        raise TimeoutError("LSL stream produced no samples during the capture")

    samples = np.concatenate(chunks, axis=0)
    rate = float(info.nominal_srate())
    if rate <= 0 and len(timestamps) >= 2:
        rate = float(1.0 / np.median(np.diff(timestamps)))
    if rate <= 0:
        raise ValueError("cannot determine LSL sample rate")
    labels = _lsl_channel_labels(info, samples.shape[1])
    channels = []
    channel_data = {}
    for channel_id, label in enumerate(labels):
        values = samples[:, channel_id]
        minimum, maximum = float(np.min(values)), float(np.max(values))
        if minimum == maximum:
            minimum, maximum = minimum - 1.0, maximum + 1.0
        channels.append(
            ChannelDef(
                label=label,
                channel_id=channel_id,
                sample_rate=rate,
                data_type=DT_FLOAT32,
                physical_min=minimum,
                physical_max=maximum,
            )
        )
        channel_data[channel_id] = values
    name = str(info.name()) or "lsl-eeg"
    return SourceFile(
        path=f"lsl://{name}",
        format="lsl",
        name=name,
        channels=channels,
        channel_data=channel_data,
    )


def _lsl_channel_labels(info, count: int) -> list[str]:
    labels = []
    try:
        channel = info.desc().child("channels").child("channel")
        for index in range(count):
            labels.append(channel.child_value("label") or f"CH{index}")
            channel = channel.next_sibling()
    except Exception:
        return [f"CH{index}" for index in range(count)]
    return labels
