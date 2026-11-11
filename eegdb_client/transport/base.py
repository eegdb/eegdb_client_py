"""Transport-independent contracts shared by remote and embedded clients."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple, Union

import numpy as np

from ..models import DT_FLOAT32, DT_FLOAT64, DT_INT16, DT_INT24, DT_INT64, Event


def numpy_dtype(data_type: int) -> np.dtype:
    """Return the canonical NumPy dtype for an EEGDB data type."""
    try:
        return np.dtype(
            {
                DT_INT16: np.int16,
                DT_INT24: np.int32,
                DT_FLOAT32: np.float32,
                DT_FLOAT64: np.float64,
                DT_INT64: np.int64,
            }[data_type]
        )
    except KeyError as exc:
        raise ValueError(f"unsupported EEGDB data type: {data_type}") from exc


class TransferClient(Protocol):
    """Operations required by the shared upload and download pipelines."""

    @property
    def is_connected(self) -> bool: ...

    def create_study(
        self,
        name: str,
        channels: List[Dict[str, Any]],
        attrs: Optional[Dict[str, Any]] = None,
        source_file: Optional[Dict[str, Any]] = None,
    ) -> str: ...

    def get_study(self, study_id: str) -> Dict[str, Any]: ...

    def write_batch(
        self,
        study_id: str,
        channel_id: int,
        data_type: int,
        start_index: int,
        data: Union[np.ndarray, List[Any]],
    ) -> None: ...

    def read_batch(
        self,
        study_id: str,
        channel_id: int,
        data_type: int,
        start_index: int,
        sample_count: int,
    ) -> Tuple[int, np.ndarray]: ...

    def read_events(
        self, study_id: str, filter_json: Optional[Dict[str, Any]] = None
    ) -> List[Event]: ...

    def write_events_json(self, study_id: str, events: List[Event]) -> None: ...

    def flush_study(self, study_id: str) -> None: ...

