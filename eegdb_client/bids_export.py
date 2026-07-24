"""Export EEGDB studies as a small BIDS EEG dataset."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .models import Event


BIDS_WRITER_NAME = "EEGDB Python Client"


def export_study_to_bids(
    client: Any,
    study_id: str,
    output_dir: str | Path,
    *,
    subject: str = "01",
    session: str = "",
    task: str = "eegdb",
    run: str = "",
    fmt: str = "edf",
    local_decode: bool = False,
    codec: str = "lz4",
    on_progress: Any = None,
) -> Path:
    from .download.fetcher import download_study

    fmt = fmt.lower()
    if fmt not in {"edf", "bdf"}:
        raise ValueError("BIDS export format must be edf or bdf")

    root = Path(output_dir)
    study = client.get_study(study_id)
    events = client.read_events_json(study_id)
    entities = bids_entities(subject=subject, session=session, task=task, run=run)
    eeg_dir = bids_eeg_dir(root, entities)
    eeg_dir.mkdir(parents=True, exist_ok=True)

    base = bids_basename(entities, "eeg")
    eeg_path = eeg_dir / f"{base}.{fmt}"
    download_study(
        client,
        study_id,
        str(eeg_path),
        fmt=fmt,
        local_decode=local_decode,
        codec=codec,
        on_progress=on_progress,
    )

    write_dataset_description(root)
    write_participants(root, study, entities)
    write_channels_tsv(eeg_dir / f"{base}_channels.tsv", study.get("channels", []))
    write_eeg_sidecar(eeg_dir / f"{base}_eeg.json", study, fmt)
    write_events_tsv(eeg_dir / f"{bids_basename(entities, 'events')}.tsv", events)
    return root


def bids_entities(*, subject: str, session: str = "", task: str = "eegdb", run: str = "") -> Dict[str, str]:
    entities = {
        "sub": normalize_entity(subject, "sub") or "01",
        "task": normalize_entity(task, "task") or "eegdb",
    }
    if session:
        entities["ses"] = normalize_entity(session, "ses")
    if run:
        entities["run"] = normalize_entity(run, "run")
    return entities


def bids_eeg_dir(root: Path, entities: Dict[str, str]) -> Path:
    path = root / f"sub-{entities['sub']}"
    if entities.get("ses"):
        path = path / f"ses-{entities['ses']}"
    return path / "eeg"


def bids_basename(entities: Dict[str, str], suffix: str) -> str:
    order = ["sub", "ses", "task", "run"]
    parts = [f"{key}-{entities[key]}" for key in order if entities.get(key)]
    parts.append(suffix)
    return "_".join(parts)


def normalize_entity(value: str, prefix: str) -> str:
    value = str(value).strip()
    if value.startswith(prefix + "-"):
        value = value[len(prefix) + 1 :]
    value = re.sub(r"[^0-9A-Za-z]+", "", value)
    return value


def write_dataset_description(root: Path) -> None:
    path = root / "dataset_description.json"
    if path.exists():
        return
    payload = {
        "Name": "EEGDB export",
        "BIDSVersion": "1.10.0",
        "DatasetType": "raw",
        "GeneratedBy": [{"Name": BIDS_WRITER_NAME}],
    }
    write_json(path, payload)


def write_participants(root: Path, study: Dict[str, Any], entities: Dict[str, str]) -> None:
    path = root / "participants.tsv"
    participant_id = f"sub-{entities['sub']}"
    rows = [{"participant_id": participant_id, "eegdb_study_id": study.get("study_id", "")}]
    write_tsv(path, ["participant_id", "eegdb_study_id"], rows)


def write_channels_tsv(path: Path, channels: Iterable[Dict[str, Any]]) -> None:
    rows = []
    for ch in channels:
        rows.append(
            {
                "name": ch.get("label", ch.get("channel_id", "")),
                "type": normalize_channel_type(ch.get("type", "EEG")),
                "units": ch.get("unit", "uV"),
                "sampling_frequency": format_number(ch.get("sample_rate", "")),
                "status": "good",
                "status_description": "n/a",
            }
        )
    write_tsv(path, ["name", "type", "units", "sampling_frequency", "status", "status_description"], rows)


def write_eeg_sidecar(path: Path, study: Dict[str, Any], fmt: str) -> None:
    channels = study.get("channels", [])
    payload = {
        "TaskName": str((study.get("attributes") or {}).get("paradigm") or "eegdb"),
        "Manufacturer": str((study.get("attributes") or {}).get("device_type") or "n/a"),
        "PowerLineFrequency": "n/a",
        "EEGReference": "n/a",
        "RecordingType": "continuous",
        "EEGChannelCount": sum(1 for ch in channels if normalize_channel_type(ch.get("type", "EEG")) == "EEG"),
        "EOGChannelCount": sum(1 for ch in channels if normalize_channel_type(ch.get("type", "")) == "EOG"),
        "ECGChannelCount": sum(1 for ch in channels if normalize_channel_type(ch.get("type", "")) == "ECG"),
        "EMGChannelCount": sum(1 for ch in channels if normalize_channel_type(ch.get("type", "")) == "EMG"),
        "MiscChannelCount": sum(1 for ch in channels if normalize_channel_type(ch.get("type", "")) == "MISC"),
        "SoftwareFilters": "n/a",
        "EEGPlacementScheme": "n/a",
        "EEGDBStudyID": study.get("study_id", ""),
        "EEGDBSourceFormat": fmt,
    }
    sample_rate = common_sample_rate(channels)
    if sample_rate is not None:
        payload["SamplingFrequency"] = sample_rate
    write_json(path, payload)


def write_events_tsv(path: Path, events: Iterable[Event]) -> None:
    rows = []
    for event in events:
        rows.append(event_tsv_row(event))
    write_tsv(
        path,
        ["onset", "duration", "trial_type", "value", "eegdb_type", "eegdb_event_id", "channel_id"],
        rows,
    )


def event_tsv_row(event: Event) -> Dict[str, str]:
    return {
        "onset": format_seconds(event.onset),
        "duration": format_seconds(event.duration),
        "trial_type": clean_tsv_value(event.code or event.type or "event"),
        "value": clean_tsv_value(event.description or event.code or "n/a"),
        "eegdb_type": clean_tsv_value(event.type or "marker"),
        "eegdb_event_id": clean_tsv_value(event.event_id or "n/a"),
        "channel_id": "n/a" if event.channel_id == 0xFFFF else str(event.channel_id),
    }


def normalize_channel_type(value: object) -> str:
    text = str(value or "").strip().upper()
    if text in {"EEG", "EOG", "ECG", "EMG", "MISC"}:
        return text
    return "MISC"


def common_sample_rate(channels: List[Dict[str, Any]]) -> float | None:
    rates = {float(ch.get("sample_rate", 0.0) or 0.0) for ch in channels}
    rates.discard(0.0)
    if len(rates) == 1:
        return next(iter(rates))
    return None


def format_seconds(value_us: int) -> str:
    return f"{float(value_us) / 1_000_000.0:.6f}".rstrip("0").rstrip(".") or "0"


def format_number(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"{number:.6f}".rstrip("0").rstrip(".")


def clean_tsv_value(value: object) -> str:
    text = str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()
    return text or "n/a"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def write_tsv(path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, delimiter="\t", fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "n/a") for key in fieldnames})
