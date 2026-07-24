"""Read BIDS EEG datasets into SourceFile objects."""

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from ..models import Event, SourceFile, StudyAttrs
from . import read_brainvision, read_edf, read_eeglab, read_fif


SUPPORTED_EEG_SUFFIXES = {
    ".edf",
    ".bdf",
    ".vhdr",
    ".fif",
    ".set",
}


@dataclass
class BIDSEEGRecord:
    path: Path
    entities: Dict[str, str]
    events_path: Optional[Path] = None
    sidecar_path: Optional[Path] = None
    participants_path: Optional[Path] = None


@dataclass
class BIDSSource:
    source: SourceFile
    attrs: StudyAttrs
    entities: Dict[str, str]


DEFAULT_BIDS_STATE_FILE = ".eegdb_import_state.json"


@dataclass
class BIDSImportState:
    root: Path
    path: Path
    records: Dict[str, Dict[str, object]]

    @classmethod
    def load(cls, root: str | Path, state_file: str = DEFAULT_BIDS_STATE_FILE) -> "BIDSImportState":
        root_path = Path(root)
        path = Path(state_file)
        if not path.is_absolute():
            path = root_path / path
        if not path.exists():
            return cls(root=root_path, path=path, records={})
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(root=root_path, path=path, records=dict(data.get("records", {})))

    def is_done(self, record: BIDSEEGRecord) -> bool:
        key = self.key(record.path)
        stored = self.records.get(key)
        if not stored:
            return False
        fp = file_fingerprint(record.path)
        return (
            stored.get("status") == "done"
            and stored.get("size") == fp["size"]
            and stored.get("mtime_ns") == fp["mtime_ns"]
            and bool(stored.get("study_id"))
        )

    def mark_done(self, record: BIDSEEGRecord, study_id: str) -> None:
        key = self.key(record.path)
        fp = file_fingerprint(record.path)
        self.records[key] = {
            "status": "done",
            "study_id": study_id,
            "size": fp["size"],
            "mtime_ns": fp["mtime_ns"],
            "entities": dict(record.entities),
        }
        self.save()

    def key(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return path.resolve().as_posix()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "records": self.records,
        }
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")


def find_bids_eeg_records(
    root: str | Path,
    *,
    subject: str = "",
    session: str = "",
    task: str = "",
    run: str = "",
) -> List[BIDSEEGRecord]:
    root_path = Path(root)
    records: List[BIDSEEGRecord] = []
    for path in sorted(root_path.rglob("*_eeg.*")):
        if path.suffix.lower() not in SUPPORTED_EEG_SUFFIXES:
            continue
        entities = parse_bids_entities(path.name)
        if not entities:
            continue
        if subject and entities.get("sub") != normalize_entity(subject, "sub"):
            continue
        if session and entities.get("ses") != normalize_entity(session, "ses"):
            continue
        if task and entities.get("task") != normalize_entity(task, "task"):
            continue
        if run and entities.get("run") != normalize_entity(run, "run"):
            continue
        base = path.with_name(path.name[: -len(path.suffix)])
        events_path = bids_sidecar(root_path, path, entities, "events", ".tsv")
        sidecar_path = bids_sidecar(root_path, path, entities, "eeg", ".json")
        participants_path = root_path / "participants.tsv"
        records.append(
            BIDSEEGRecord(
                path=path,
                entities=entities,
                events_path=events_path if events_path and events_path.exists() else None,
                sidecar_path=sidecar_path if sidecar_path and sidecar_path.exists() else None,
                participants_path=participants_path if participants_path.exists() else None,
            )
        )
        _ = base
    return records


def file_fingerprint(path: Path) -> Dict[str, int]:
    stat = path.stat()
    return {"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}


def read_bids_eeg_record(record: BIDSEEGRecord) -> BIDSSource:
    source = read_bids_signal_file(record.path)
    events = read_bids_events(record.events_path) if record.events_path else []
    if events:
        source.events = events
    source.format = f"bids-{source.format}"
    source.name = bids_study_name(record.entities, source.name)

    attrs = bids_attrs(record)
    return BIDSSource(source=source, attrs=attrs, entities=dict(record.entities))


def read_bids_signal_file(path: Path) -> SourceFile:
    ext = path.suffix.lower()
    if ext == ".fif":
        return read_fif(str(path))
    if ext == ".vhdr":
        return read_brainvision(str(path))
    if ext == ".set":
        return read_eeglab(str(path))
    if ext in (".edf", ".bdf"):
        return read_edf(str(path))
    raise ValueError(f"unsupported BIDS EEG file: {path}")


def parse_bids_entities(filename: str) -> Dict[str, str]:
    stem = filename
    for suffix in SUPPORTED_EEG_SUFFIXES:
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    if stem.endswith("_eeg"):
        stem = stem[:-4]
    entities: Dict[str, str] = {}
    for part in stem.split("_"):
        if "-" not in part:
            continue
        key, value = part.split("-", 1)
        entities[key] = value
    return entities


def normalize_entity(value: str, prefix: str) -> str:
    value = value.strip()
    if value.startswith(prefix + "-"):
        return value[len(prefix) + 1 :]
    return value


def bids_sidecar(root: Path, data_path: Path, entities: Dict[str, str], suffix: str, ext: str) -> Optional[Path]:
    candidates = []
    prefixes = []
    order = ["sub", "ses", "task", "acq", "run"]
    for key in order:
        if key in entities:
            prefixes.append(f"{key}-{entities[key]}")
            candidates.append(data_path.with_name("_".join(prefixes + [suffix]) + ext))
    candidates.append(root / ("_".join(prefixes + [suffix]) + ext))
    for candidate in reversed(candidates):
        if candidate.exists():
            return candidate
    return None


def read_bids_events(path: Path) -> List[Event]:
    events: List[Event] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for idx, row in enumerate(reader, start=1):
            if not row:
                continue
            onset = parse_float(row.get("onset", ""))
            duration = parse_float(row.get("duration", "0"))
            if onset is None:
                continue
            trial_type = clean_text(row.get("trial_type") or row.get("event_type") or row.get("type") or "")
            value = clean_text(row.get("value") or row.get("stim_file") or row.get("response") or "")
            code = clean_code(trial_type or value or f"event_{idx}")
            event_type = infer_bids_event_type(row, code)
            attrs = {k: clean_text(v) for k, v in row.items() if v not in (None, "", "n/a")}
            attrs["bids_row"] = str(idx)
            trial_id = clean_text(row.get("trial_id") or row.get("trial") or "")
            if not trial_id:
                trial_id = f"trial-{idx:06d}"
            duration_us = int(duration * 1_000_000) if duration is not None else 0
            if event_type == "artifact" and duration_us <= 0:
                duration_us = 1
            events.append(
                Event(
                    type=event_type,
                    onset=int(onset * 1_000_000),
                    duration=duration_us,
                    channel_id=0xFFFF,
                    code=code,
                    description=trial_type or value or code,
                    trial_id=trial_id,
                    source="bids",
                    attributes=attrs,
                )
            )
    return events


def infer_bids_event_type(row: Dict[str, str], code: str) -> str:
    raw = " ".join(clean_text(row.get(k, "")) for k in ("type", "event_type", "trial_type", "value", "response"))
    low = raw.lower()
    code_low = code.lower()
    if "artifact" in low or "bad" in low or code_low.startswith("bad"):
        return "artifact"
    if "response" in low or "button" in low or "keypress" in low:
        return "response"
    if "marker" in low or "boundary" in low or "sync" in low:
        return "marker"
    return "stimulus"


def bids_attrs(record: BIDSEEGRecord) -> StudyAttrs:
    custom: Dict[str, str] = {}
    for key, value in record.entities.items():
        custom[f"bids_{key}"] = value
    if record.sidecar_path:
        with record.sidecar_path.open("r", encoding="utf-8") as fh:
            sidecar = json.load(fh)
        for key, value in sidecar.items():
            if value is None:
                continue
            custom[f"bids_{key}"] = str(value)
    subject = record.entities.get("sub", "")
    if record.participants_path and subject:
        participant = participant_row(record.participants_path, subject)
        for key, value in participant.items():
            custom[f"participant_{key}"] = value
    return StudyAttrs(
        paradigm=record.entities.get("task", ""),
        session=record.entities.get("ses", ""),
        custom=custom,
    )


def participant_row(path: Path, subject: str) -> Dict[str, str]:
    wanted = "sub-" + subject
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            if row.get("participant_id") == wanted:
                return {k: clean_text(v) for k, v in row.items() if v not in (None, "", "n/a")}
    return {}


def bids_study_name(entities: Dict[str, str], fallback: str) -> str:
    parts = []
    for key in ("sub", "ses", "task", "run"):
        if entities.get(key):
            parts.append(f"{key}-{entities[key]}")
    return "_".join(parts) if parts else fallback


def parse_float(value: str) -> Optional[float]:
    value = clean_text(value)
    if value == "" or value.lower() == "n/a":
        return None
    return float(value)


def clean_text(value: object) -> str:
    return str(value).strip()


def clean_code(value: str) -> str:
    value = value.strip().replace(" ", "_")
    value = re.sub(r"[^0-9A-Za-z_.:-]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_") or "event"
