"""BIDS EEG dataset discovery and metadata/event mapping."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import re

from ..models import Event, SourceFile, StudyAttrs

_PRIMARY_EXTENSIONS = {".edf", ".bdf", ".fif", ".vhdr", ".set", ".xdf", ".cdt"}
_ENTITY_RE = re.compile(r"(?:^|_)(sub|ses|task|run|acq)-([^_]+)")


@dataclass(frozen=True)
class BIDSRecording:
    path: Path
    attrs: StudyAttrs


def discover_bids_recordings(root: str | Path) -> list[BIDSRecording]:
    root_path = Path(root).expanduser().resolve()
    if not (root_path / "dataset_description.json").is_file():
        raise ValueError(f"not a BIDS dataset (missing dataset_description.json): {root_path}")
    recordings = []
    for path in sorted(root_path.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _PRIMARY_EXTENSIONS:
            continue
        if "derivatives" in path.relative_to(root_path).parts:
            continue
        if "_eeg" not in path.stem and path.suffix.lower() != ".cdt":
            continue
        entities = dict(_ENTITY_RE.findall(path.stem))
        custom = {
            f"bids_{key}": value
            for key, value in entities.items()
            if key in {"sub", "run", "acq"}
        }
        recordings.append(
            BIDSRecording(
                path=path,
                attrs=StudyAttrs(
                    paradigm=entities.get("task", ""),
                    session=entities.get("ses", ""),
                    custom=custom,
                ),
            )
        )
    return recordings


def attach_bids_events(source: SourceFile, recording_path: str | Path) -> SourceFile:
    path = Path(recording_path)
    events_path = path.with_name(re.sub(r"_eeg$", "_events", path.stem) + ".tsv")
    if not events_path.is_file():
        return source
    events = []
    with events_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            try:
                onset = int(round(float(row.get("onset", "0")) * 1_000_000))
                duration = int(round(float(row.get("duration", "0") or 0) * 1_000_000))
            except ValueError as exc:
                raise ValueError(f"invalid BIDS event timing in {events_path}") from exc
            code = row.get("trial_type") or row.get("value") or "event"
            events.append(
                Event(
                    onset=onset,
                    duration=duration,
                    type="stimulus",
                    code=code,
                    description=code,
                    source="bids",
                    attributes={
                        key: value
                        for key, value in row.items()
                        if key not in {"onset", "duration", "trial_type", "value"}
                        and value not in {None, "", "n/a"}
                    },
                )
            )
    source.events = events
    return source
