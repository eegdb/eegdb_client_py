from pathlib import Path

from eegdb_client.bids_export import bids_basename, bids_eeg_dir, bids_entities, event_tsv_row, write_channels_tsv
from eegdb_client.models import Event


def test_bids_export_entities_and_paths(tmp_path: Path):
    entities = bids_entities(subject="sub-01", session="ses-A", task="task-oddball", run="01")

    assert entities == {"sub": "01", "task": "oddball", "ses": "A", "run": "01"}
    assert bids_basename(entities, "eeg") == "sub-01_ses-A_task-oddball_run-01_eeg"
    assert bids_eeg_dir(tmp_path, entities) == tmp_path / "sub-01" / "ses-A" / "eeg"


def test_bids_export_event_row_uses_standard_event_fields():
    row = event_tsv_row(
        Event(
            event_id="evt-1",
            type="response",
            onset=1_250_000,
            duration=300_000,
            channel_id=0xFFFF,
            code="button",
            description="button press",
        )
    )

    assert row["onset"] == "1.25"
    assert row["duration"] == "0.3"
    assert row["trial_type"] == "button"
    assert row["value"] == "button press"
    assert row["eegdb_type"] == "response"
    assert row["eegdb_event_id"] == "evt-1"
    assert row["channel_id"] == "n/a"


def test_write_channels_tsv(tmp_path: Path):
    path = tmp_path / "channels.tsv"
    write_channels_tsv(
        path,
        [
            {"label": "Cz", "type": "EEG", "unit": "uV", "sample_rate": 256.0},
            {"label": "HEOG", "type": "EOG", "unit": "uV", "sample_rate": 256.0},
        ],
    )

    assert path.read_text(encoding="utf-8").splitlines() == [
        "name\ttype\tunits\tsampling_frequency\tstatus\tstatus_description",
        "Cz\tEEG\tuV\t256\tgood\tn/a",
        "HEOG\tEOG\tuV\t256\tgood\tn/a",
    ]
