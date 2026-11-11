"""Embedded EEGDB client backed by the optional eegdb-storage package."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np

from ..models import Event
from .base import numpy_dtype


class EEGDBStorageClient:
    """Use one local EEGDB storage directory without a server or TCP session.

    A storage directory is process-exclusive. Do not open a directory that is
    already owned by an EEGDB server or another embedded client.
    """

    def __init__(self, path: str | Path, *, library_path: str | Path | None = None):
        self.path = Path(path).expanduser().resolve()
        self.library_path = library_path
        self._storage: Any = None
        # Retain the checkpoint fields used by existing resumable uploads. The
        # resolved path is the embedded equivalent of a remote database target.
        self.host = "local"
        self.port = 0
        self.database = str(self.path)

    @property
    def is_connected(self) -> bool:
        return self._storage is not None

    def connect(self) -> None:
        if self._storage is not None:
            return
        try:
            from eegdb_storage import Storage
        except ImportError as exc:
            raise RuntimeError(
                "embedded mode requires eegdb-storage; install eegdb-client[embedded]"
            ) from exc
        self._storage = Storage(self.path, library_path=self.library_path)

    def close(self) -> None:
        storage, self._storage = self._storage, None
        if storage is not None:
            storage.close()

    def __enter__(self) -> "EEGDBStorageClient":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _store(self):
        if self._storage is None:
            raise RuntimeError("embedded storage is not open")
        return self._storage

    def create_study(
        self,
        name: str,
        channels: List[Dict[str, Any]],
        attrs: Optional[Dict[str, Any]] = None,
        source_file: Optional[Dict[str, Any]] = None,
    ) -> str:
        study: Dict[str, Any] = {
            "name": name,
            "channels": channels,
            "attributes": attrs or {},
        }
        if source_file:
            study["source_file"] = source_file
        return str(self._store().create_study(study))

    def list_studies(self) -> List[Dict[str, Any]]:
        store = self._store()
        return [
            self._normalize_study(store.get_study(study_id))
            for study_id in store.list_studies()
        ]

    def get_study(self, study_id: str) -> Dict[str, Any]:
        return self._normalize_study(self._store().get_study(study_id))

    @staticmethod
    def _normalize_study(study: Dict[str, Any]) -> Dict[str, Any]:
        """Fill presentation fields supplied directly by the TCP protocol."""
        result = dict(study)
        result.setdefault("channels", [])
        result.setdefault("num_channels", len(result["channels"]))
        return result

    def search_studies(self, attrs: Dict[str, str]) -> List[Dict[str, Any]]:
        def matches(study: Dict[str, Any]) -> bool:
            values = study.get("attributes") or {}
            return all(str(values.get(key, "")) == str(value) for key, value in attrs.items())

        return [study for study in self.list_studies() if matches(study)]

    def update_study(
        self,
        study_id: str,
        *,
        name: Optional[str] = None,
        attrs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if name is None and attrs is None:
            raise ValueError("name or attrs is required")
        study = self.get_study(study_id)
        if name is not None:
            study["name"] = name
        if attrs is not None:
            study["attributes"] = attrs
        self._store().update_study(study)
        return self.get_study(study_id)

    def delete_study(self, study_id: str) -> str:
        self._store().delete_study(study_id)
        return study_id

    def write_batch(
        self,
        study_id: str,
        channel_id: int,
        data_type: int,
        start_index: int,
        data: Union[np.ndarray, List[Any]],
    ) -> None:
        method = {
            0x01: "write_int16",
            0x02: "write_int24",
            0x03: "write_float32",
            0x04: "write_float64",
            0x05: "write_int64",
        }.get(data_type)
        if method is None:
            raise ValueError(f"unsupported EEGDB data type: {data_type}")
        values = data.tolist() if isinstance(data, np.ndarray) else list(data)
        getattr(self._store(), method)(study_id, channel_id, start_index, values)

    def read_batch(
        self,
        study_id: str,
        channel_id: int,
        data_type: int,
        start_index: int,
        sample_count: int,
    ) -> tuple[int, np.ndarray]:
        if sample_count <= 0:
            raise ValueError("sample_count must be positive")
        method = {
            0x01: "read_int16",
            0x02: "read_int24",
            0x03: "read_float32",
            0x04: "read_float64",
            0x05: "read_int64",
        }.get(data_type)
        if method is None:
            raise ValueError(f"unsupported EEGDB data type: {data_type}")
        values = getattr(self._store(), method)(
            study_id, channel_id, start_index, start_index + sample_count
        )
        return start_index, np.asarray(values, dtype=numpy_dtype(data_type))

    def read_compressed_batch(self, *_: Any, **__: Any):
        raise ValueError("compressed transfer is only available with the TCP backend")

    def write_events_json(self, study_id: str, events: List[Event]) -> None:
        self._store().append_events(study_id, [event.to_dict() for event in events])

    def read_events(
        self, study_id: str, filter_json: Optional[Dict[str, Any]] = None
    ) -> List[Event]:
        events = self._store().query_events(study_id, filter_json)
        return [Event.from_dict(event) for event in events]

    def flush_study(self, study_id: str) -> None:
        self._store().flush(study_id)

