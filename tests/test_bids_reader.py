from pathlib import Path

from eegdb_client.readers.bids_reader import (
    BIDSImportState,
    find_bids_eeg_records,
    parse_bids_entities,
    read_bids_events,
)


def test_parse_bids_entities():
    got = parse_bids_entities("sub-01_ses-02_task-oddball_run-1_eeg.vhdr")

    assert got == {
        "sub": "01",
        "ses": "02",
        "task": "oddball",
        "run": "1",
    }


def test_find_bids_eeg_records(tmp_path: Path):
    eeg_dir = tmp_path / "sub-01" / "ses-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    data = eeg_dir / "sub-01_ses-01_task-rest_run-1_eeg.vhdr"
    data.write_text("Brain Vision Data Exchange Header File Version 1.0", encoding="utf-8")
    events = eeg_dir / "sub-01_ses-01_task-rest_run-1_events.tsv"
    events.write_text("onset\tduration\ttrial_type\n0.5\t0.1\tStimulus/S 1\n", encoding="utf-8")

    records = find_bids_eeg_records(tmp_path, subject="sub-01", task="rest")

    assert len(records) == 1
    assert records[0].path == data
    assert records[0].events_path == events
    assert records[0].entities["run"] == "1"


def test_read_bids_events(tmp_path: Path):
    path = tmp_path / "sub-01_task-test_events.tsv"
    path.write_text(
        "onset\tduration\ttrial_type\tresponse\tcorrect\n"
        "1.0\t0.0\ttarget\t\t\n"
        "1.4\t0.0\tresponse\tbutton_left\ttrue\n"
        "2.0\t0.5\tbad_artifact\t\t\n",
        encoding="utf-8",
    )

    events = read_bids_events(path)

    assert len(events) == 3
    assert events[0].type == "stimulus"
    assert events[0].onset == 1_000_000
    assert events[1].type == "response"
    assert events[1].attributes["correct"] == "true"
    assert events[2].type == "artifact"
    assert events[2].duration == 500_000


def test_bids_import_state_tracks_done_records(tmp_path: Path):
    eeg_dir = tmp_path / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    data = eeg_dir / "sub-01_task-rest_eeg.vhdr"
    data.write_text("header", encoding="utf-8")
    records = find_bids_eeg_records(tmp_path)
    assert len(records) == 1

    state = BIDSImportState.load(tmp_path)
    assert not state.is_done(records[0])

    state.mark_done(records[0], "study-1")
    reloaded = BIDSImportState.load(tmp_path)
    assert reloaded.is_done(records[0])

    data.write_text("changed", encoding="utf-8")
    assert not reloaded.is_done(records[0])
