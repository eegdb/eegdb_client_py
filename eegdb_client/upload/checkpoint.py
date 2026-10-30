"""Durable client-side checkpoints for resumable uploads."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from platformdirs import user_state_dir


@dataclass
class UploadCheckpoint:
    source_path: str
    source_size: int
    source_mtime_ns: int
    host: str
    port: int
    database: str
    study_id: str
    next_window_start: int = 0
    events_complete: bool = False
    version: int = 1

    @classmethod
    def load(cls, path: Path) -> "UploadCheckpoint":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError(f"unsupported upload checkpoint: {path}")
        return cls(**data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(path.name + ".tmp")
        temp_path.write_text(
            json.dumps(asdict(self), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)

    def validate(self, source_path: str, client: Any) -> None:
        identity = source_identity(source_path)
        expected = (
            identity["source_path"],
            identity["source_size"],
            identity["source_mtime_ns"],
            str(getattr(client, "host", "")),
            int(getattr(client, "port", 0)),
            str(getattr(client, "database", "default")),
        )
        actual = (
            self.source_path,
            self.source_size,
            self.source_mtime_ns,
            self.host,
            self.port,
            self.database,
        )
        if actual != expected:
            raise ValueError(
                "upload checkpoint does not match the source file or EEGDB target; "
                "use a different checkpoint or restart the upload"
            )


def source_identity(source_path: str) -> dict[str, Any]:
    path = Path(source_path).expanduser().resolve()
    stat = path.stat()
    return {
        "source_path": str(path),
        "source_size": stat.st_size,
        "source_mtime_ns": stat.st_mtime_ns,
    }


def default_checkpoint_path(source_path: str, client: Any) -> Path:
    target = "\0".join(
        (
            str(Path(source_path).expanduser().resolve()),
            str(getattr(client, "host", "")),
            str(getattr(client, "port", 0)),
            str(getattr(client, "database", "default")),
        )
    )
    key = hashlib.sha256(target.encode("utf-8")).hexdigest()[:24]
    return Path(user_state_dir("EEGDBClient", ensure_exists=True)) / "transfers" / f"{key}.json"
