"""Notebook-friendly chunk, DataFrame, Arrow, and trial containers."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Iterable, Iterator

import numpy as np
import pandas as pd


@dataclass
class SignalChunk:
    study_id: str
    start_index: int
    end_index: int
    channel_ids: list[int]
    data: np.ndarray
    units: list[str]

    def to_pandas(self, *, long: bool = False) -> pd.DataFrame:
        frame = pd.DataFrame(
            self.data.T,
            index=pd.RangeIndex(self.start_index, self.end_index, name="sample_index"),
            columns=[f"ch_{channel_id}" for channel_id in self.channel_ids],
        )
        if not long:
            return frame
        return frame.reset_index().melt(
            id_vars="sample_index", var_name="channel", value_name="value"
        )

    def to_arrow(self):
        try:
            import pyarrow as pa
        except ImportError as exc:
            raise ImportError("Arrow conversion requires pyarrow") from exc
        return pa.Table.from_pandas(self.to_pandas().reset_index(), preserve_index=False)


@dataclass
class EEGDBTrials:
    study_id: str
    trials: list[dict[str, Any]]

    @classmethod
    def from_response(cls, response: dict[str, Any]) -> "EEGDBTrials":
        return cls(
            study_id=str(response.get("study_id", "")),
            trials=list(response.get("trials") or []),
        )

    @classmethod
    def from_server(cls, client: Any, study_id: str, **filters: Any) -> "EEGDBTrials":
        return cls.from_response(client.query_trials(study_id, **filters))

    def to_pandas(self) -> pd.DataFrame:
        return pd.json_normalize(self.trials)

    def __len__(self) -> int:
        return len(self.trials)


def iter_signal_chunks(
    client: Any,
    study_id: str,
    channel_ids: Iterable[int],
    *,
    start: int = 0,
    end: int | None = None,
    chunk_samples: int = 8192,
    physical: bool = True,
    references: Iterable[int] = (),
) -> Iterator[SignalChunk]:
    channel_ids = [int(value) for value in channel_ids]
    if not channel_ids:
        raise ValueError("at least one channel is required")
    if chunk_samples <= 0:
        raise ValueError("chunk_samples must be positive")
    if end is None:
        study = client.get_study(study_id)
        end = int(study.get("end_index") or study.get("num_samples") or 0)
    if end < start:
        raise ValueError("end must be greater than or equal to start")

    for chunk_start in range(start, end, chunk_samples):
        chunk_end = min(end, chunk_start + chunk_samples)
        response = client.query_channels(
            study_id,
            channel_ids,
            idx_start=chunk_start,
            idx_end=chunk_end,
            physical=physical,
            references=references,
        )
        channels = response.get("channels") or []
        by_id = {int(channel["channel_id"]): channel for channel in channels}
        arrays = [
            np.asarray(by_id[channel_id].get("samples") or [], dtype=np.float64)
            for channel_id in channel_ids
        ]
        sample_count = min((len(array) for array in arrays), default=0)
        if sample_count == 0:
            break
        yield SignalChunk(
            study_id=study_id,
            start_index=chunk_start,
            end_index=chunk_start + sample_count,
            channel_ids=channel_ids,
            data=np.stack([array[:sample_count] for array in arrays]),
            units=[str(by_id[channel_id].get("unit", "")) for channel_id in channel_ids],
        )


def read_arrow_table(
    client: Any,
    study_id: str,
    channel_id: int,
    *,
    start: int | None = None,
    end: int | None = None,
):
    try:
        import pyarrow.ipc as ipc
    except ImportError as exc:
        raise ImportError("Arrow reads require pyarrow") from exc
    payload = client.query_channel_arrow(
        study_id, channel_id, idx_start=start, idx_end=end
    )
    return ipc.open_stream(BytesIO(payload)).read_all()
