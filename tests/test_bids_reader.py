from pathlib import Path

from eegdb_client.models import SourceFile
from eegdb_client.readers.bids import attach_bids_events, discover_bids_recordings
from eegdb_client.readers.xdf_reader import (
    _channel_labels,
    _marker_events,
    _select_eeg_stream,
)
from eegdb_client.readers.lsl_reader import record_lsl
from eegdb_client.readers.mne_common import _annotations_to_events


def test_bids_discovery_maps_filename_entities(tmp_path: Path):
    (tmp_path / "dataset_description.json").write_text(
        '{"Name":"demo","BIDSVersion":"1.9.0"}', encoding="utf-8"
    )
    eeg_dir = tmp_path / "sub-01" / "ses-02" / "eeg"
    eeg_dir.mkdir(parents=True)
    recording = eeg_dir / "sub-01_ses-02_task-rest_run-03_eeg.edf"
    recording.touch()
    derivatives = tmp_path / "derivatives" / "sub-01_task-rest_eeg.edf"
    derivatives.parent.mkdir()
    derivatives.touch()

    found = discover_bids_recordings(tmp_path)

    assert len(found) == 1
    assert found[0].path == recording
    assert found[0].attrs.paradigm == "rest"
    assert found[0].attrs.session == "02"
    assert found[0].attrs.custom == {"bids_sub": "01", "bids_run": "03"}


def test_bids_events_tsv_replaces_source_events(tmp_path: Path):
    recording = tmp_path / "sub-01_task-oddball_eeg.edf"
    events = tmp_path / "sub-01_task-oddball_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\tresponse_time\n"
        "1.25\t0.5\ttarget\t0.42\n",
        encoding="utf-8",
    )
    source = SourceFile(path=str(recording), format="edf", name="demo", channels=[])

    attach_bids_events(source, recording)

    assert len(source.events) == 1
    assert source.events[0].onset == 1_250_000
    assert source.events[0].duration == 500_000
    assert source.events[0].code == "target"
    assert source.events[0].attributes == {"response_time": "0.42"}


def test_xdf_helpers_select_eeg_labels_and_relative_markers():
    eeg = {
        "info": {
            "type": ["EEG"],
            "nominal_srate": ["256"],
            "desc": [{"channels": [{"channel": [{"label": ["Cz"]}]}]}],
        },
        "time_stamps": [10.0, 10.1],
    }
    markers = {
        "info": {"type": ["Markers"]},
        "time_stamps": [10.25],
        "time_series": [["target"]],
    }

    assert _select_eeg_stream([markers, eeg]) is eeg
    assert _channel_labels(eeg, 2) == ["Cz", "CH1"]
    events = _marker_events([eeg, markers], eeg)
    assert [(event.onset, event.code, event.source) for event in events] == [
        (250_000, "target", "xdf")
    ]


def test_lsl_capture_builds_uploadable_source(monkeypatch):
    class XMLNode:
        def __init__(self, labels=None, index=0):
            self.labels = labels or ["C3", "C4"]
            self.index = index

        def child(self, name):
            return self

        def child_value(self, name):
            return self.labels[self.index]

        def next_sibling(self):
            return XMLNode(self.labels, min(self.index + 1, len(self.labels) - 1))

    class Info:
        def nominal_srate(self):
            return 100.0

        def name(self):
            return "demo-lsl"

        def desc(self):
            return XMLNode()

    class Inlet:
        def __init__(self, info):
            pass

        def pull_chunk(self, timeout, max_samples):
            return [[1.0, 2.0], [3.0, 4.0]], [10.0, 10.01]

    import pylsl

    monkeypatch.setattr(pylsl, "resolve_byprop", lambda *args, **kwargs: [Info()])
    monkeypatch.setattr(pylsl, "StreamInlet", Inlet)
    ticks = iter([0.0, 0.1, 0.2, 0.6])
    monkeypatch.setattr("eegdb_client.readers.lsl_reader.time.monotonic", lambda: next(ticks))

    source = record_lsl(0.5)

    assert source.name == "demo-lsl"
    assert [channel.label for channel in source.channels] == ["C3", "C4"]
    assert source.channel_data[0].tolist() == [1.0, 3.0]


def test_mne_annotations_use_valid_marker_event_type():
    import mne

    info = mne.create_info(["Cz"], 100, ch_types="eeg")
    raw = mne.io.RawArray([[0.0] * 100], info, verbose=False)
    raw.set_annotations(mne.Annotations([0.25], [0.1], ["stimulus-1"]))

    events = _annotations_to_events(raw)

    assert events[0].type == "marker"
    assert events[0].source == "mne"
