"""Notebook-friendly EEGDB epoch container and MNE conversion helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np


@dataclass
class EEGDBEpochs:
    study_id: str
    data: np.ndarray
    sample_rate: float
    time_axis_ms: np.ndarray
    channel_ids: List[int]
    channel_names: List[str]
    events: List[Dict[str, Any]]
    units: List[str] = field(default_factory=list)
    metadata: List[Dict[str, Any]] = field(default_factory=list)
    rejected_count: int = 0

    @classmethod
    def from_server(
        cls,
        client: Any,
        study_id: str,
        *,
        channels: Optional[List[int]] = None,
        event_type: str = "stimulus",
        code: str = "",
        trial_id: str = "",
        source: str = "",
        pre_ms: int = 200,
        post_ms: int = 800,
        physical: bool = True,
        reference: Optional[List[int]] = None,
        reject_artifact: bool = False,
        include_artifacts: bool = False,
    ) -> "EEGDBEpochs":
        response = client.query_epochs(
            study_id,
            channels=channels,
            event_type=event_type,
            code=code,
            trial_id=trial_id,
            source=source,
            pre_ms=pre_ms,
            post_ms=post_ms,
            physical=physical,
            reference=reference,
            reject_artifact=reject_artifact,
            include_artifacts=include_artifacts,
        )
        return cls.from_response(response)

    @classmethod
    def from_http(
        cls,
        base_url: str,
        study_id: str,
        *,
        channels: Optional[List[int]] = None,
        event_type: str = "stimulus",
        code: str = "",
        trial_id: str = "",
        source: str = "",
        pre_ms: int = 200,
        post_ms: int = 800,
        physical: bool = True,
        reference: Optional[List[int]] = None,
        reject_artifact: bool = False,
        include_artifacts: bool = False,
        timeout: float = 120,
    ) -> "EEGDBEpochs":
        response = query_epochs_http(
            base_url,
            study_id,
            channels=channels,
            event_type=event_type,
            code=code,
            trial_id=trial_id,
            source=source,
            pre_ms=pre_ms,
            post_ms=post_ms,
            physical=physical,
            reference=reference,
            reject_artifact=reject_artifact,
            include_artifacts=include_artifacts,
            timeout=timeout,
        )
        return cls.from_response(response)

    @classmethod
    def from_response(cls, response: Dict[str, Any]) -> "EEGDBEpochs":
        epochs = list(response.get("epochs") or [])
        channel_ids = [int(ch) for ch in (response.get("channels") or infer_channel_ids(epochs))]
        sample_rate = float(response.get("sample_rate") or infer_sample_rate(epochs) or 0.0)
        data, channel_names, units = epoch_tensor(epochs, channel_ids)
        pre_ms = int(response.get("pre_ms") or 0)
        events = [dict(epoch.get("event") or {}) for epoch in epochs]
        metadata = [epoch_metadata(epoch) for epoch in epochs]
        return cls(
            study_id=str(response.get("study_id", "")),
            data=data,
            sample_rate=sample_rate,
            time_axis_ms=time_axis_ms(pre_ms, data.shape[-1], sample_rate),
            channel_ids=channel_ids,
            channel_names=channel_names,
            events=events,
            units=units,
            metadata=metadata,
            rejected_count=int(response.get("rejected_count") or 0),
        )

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.data.shape

    @property
    def tmin(self) -> float:
        if self.time_axis_ms.size == 0:
            return 0.0
        return float(self.time_axis_ms[0]) / 1000.0

    def average(self) -> np.ndarray:
        if self.data.shape[0] == 0:
            return np.empty((len(self.channel_ids), 0), dtype=np.float64)
        return self.data.mean(axis=0)

    def to_mne(self, *, scale_units: bool = True, ch_types: str | List[str] = "eeg") -> Any:
        import mne

        data = self.data.astype(np.float64, copy=True)
        if scale_units:
            for idx, unit in enumerate(self.units):
                data[:, idx, :] *= unit_scale_to_volts(unit)
        info = mne.create_info(ch_names=self.channel_names, sfreq=self.sample_rate, ch_types=ch_types)
        events, event_id = mne_events(self.events, self.sample_rate)
        metadata = None
        if self.metadata:
            import pandas as pd

            metadata = pd.DataFrame(self.metadata)
        return mne.EpochsArray(data, info, events=events, event_id=event_id, tmin=self.tmin, metadata=metadata)


def epoch_tensor(epochs: List[Dict[str, Any]], channel_ids: List[int]) -> tuple[np.ndarray, List[str], List[str]]:
    if not epochs:
        return np.empty((0, len(channel_ids), 0), dtype=np.float64), [str(ch) for ch in channel_ids], []

    first_channels = channels_by_id(epochs[0].get("channels") or [])
    sample_count = 0
    for channel_id in channel_ids:
        samples = first_channels.get(channel_id, {}).get("samples") or []
        sample_count = max(sample_count, len(samples))

    data = np.zeros((len(epochs), len(channel_ids), sample_count), dtype=np.float64)
    channel_names: List[str] = []
    units: List[str] = []
    for channel_id in channel_ids:
        first = first_channels.get(channel_id, {})
        channel_names.append(str(first.get("label") or f"CH{channel_id}"))
        units.append(str(first.get("unit") or ""))

    for epoch_index, epoch in enumerate(epochs):
        by_id = channels_by_id(epoch.get("channels") or [])
        for ch_index, channel_id in enumerate(channel_ids):
            samples = np.asarray(by_id.get(channel_id, {}).get("samples") or [], dtype=np.float64)
            if len(samples) != sample_count:
                raise ValueError(
                    f"epoch {epoch_index} channel {channel_id} has {len(samples)} samples, expected {sample_count}"
                )
            data[epoch_index, ch_index, :] = samples
    return data, channel_names, units


def query_epochs_http(
    base_url: str,
    study_id: str,
    *,
    channels: Optional[List[int]] = None,
    event_type: str = "stimulus",
    code: str = "",
    trial_id: str = "",
    source: str = "",
    pre_ms: int = 200,
    post_ms: int = 800,
    physical: bool = True,
    reference: Optional[List[int]] = None,
    reject_artifact: bool = False,
    include_artifacts: bool = False,
    timeout: float = 120,
) -> Dict[str, Any]:
    params: Dict[str, str] = {
        "pre_ms": str(pre_ms),
        "post_ms": str(post_ms),
        "physical": "true" if physical else "false",
    }
    if channels:
        params["channels"] = ",".join(str(ch) for ch in channels)
    if event_type:
        params["type"] = event_type
    if code:
        params["code"] = code
    if trial_id:
        params["trial_id"] = trial_id
    if source:
        params["source"] = source
    if reference:
        params["reference"] = ",".join(str(ch) for ch in reference)
    if reject_artifact:
        params["reject_artifact"] = "true"
    if include_artifacts:
        params["include_artifacts"] = "true"

    url = f"{base_url.rstrip('/')}/api/v1/studies/{study_id}/epochs?{urlencode(params)}"
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def channels_by_id(channels: Iterable[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    return {int(ch.get("channel_id")): dict(ch) for ch in channels}


def infer_channel_ids(epochs: List[Dict[str, Any]]) -> List[int]:
    if not epochs:
        return []
    return [int(ch.get("channel_id")) for ch in (epochs[0].get("channels") or [])]


def infer_sample_rate(epochs: List[Dict[str, Any]]) -> float:
    for epoch in epochs:
        for channel in epoch.get("channels") or []:
            value = channel.get("effective_sample_rate") or channel.get("sample_rate")
            if value:
                return float(value)
    return 0.0


def time_axis_ms(pre_ms: int, samples: int, sample_rate: float) -> np.ndarray:
    if samples <= 0:
        return np.empty(0, dtype=np.float64)
    if sample_rate <= 0:
        return np.arange(samples, dtype=np.float64) - float(pre_ms)
    return -float(pre_ms) + np.arange(samples, dtype=np.float64) * 1000.0 / sample_rate


def epoch_metadata(epoch: Dict[str, Any]) -> Dict[str, Any]:
    event = dict(epoch.get("event") or {})
    return {
        "trial_id": event.get("trial_id", ""),
        "event_type": event.get("type", ""),
        "event_code": event.get("code", ""),
        "event_onset_us": event.get("onset_us", 0),
        "has_artifact": bool(epoch.get("has_artifact")),
    }


def mne_events(events: List[Dict[str, Any]], sample_rate: float) -> tuple[np.ndarray, Dict[str, int]]:
    event_id: Dict[str, int] = {}
    out = np.zeros((len(events), 3), dtype=np.int64)
    for idx, event in enumerate(events):
        label = str(event.get("code") or event.get("type") or "event")
        if label not in event_id:
            event_id[label] = len(event_id) + 1
        onset_us = int(event.get("onset_us") or event.get("onset") or idx)
        out[idx] = [int(round(onset_us * sample_rate / 1_000_000.0)), 0, event_id[label]]
    return out, event_id


def unit_scale_to_volts(unit: str) -> float:
    unit = unit.strip().lower()
    if unit in {"uv", "microvolt", "microvolts"}:
        return 1e-6
    if unit in {"mv", "millivolt", "millivolts"}:
        return 1e-3
    return 1.0
