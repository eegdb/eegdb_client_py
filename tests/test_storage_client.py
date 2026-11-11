from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np

from eegdb_client.models import DT_INT16, Event
from eegdb_client.transport.storage_client import EEGDBStorageClient


class FakeStorage:
    def __init__(self, path, library_path=None):
        self.path = path
        self.library_path = library_path
        self.closed = False
        self.study = None
        self.samples = []
        self.events = []

    def close(self):
        self.closed = True

    def create_study(self, study):
        self.study = {**study, "study_id": "101", "num_samples": 3}
        return "101"

    def list_studies(self):
        return ["101"]

    def get_study(self, study_id):
        assert study_id == "101"
        return dict(self.study)

    def update_study(self, study):
        self.study = dict(study)

    def delete_study(self, study_id):
        self.study = None

    def write_int16(self, study_id, channel_id, start_index, values):
        self.samples = list(values)

    def read_int16(self, study_id, channel_id, start_index, end_index):
        return self.samples[start_index:end_index]

    def append_events(self, study_id, events):
        self.events.extend(events)

    def query_events(self, study_id, event_filter):
        return list(self.events)

    def flush(self, study_id):
        return None


def test_embedded_client_adapts_storage_api(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "eegdb_storage", SimpleNamespace(Storage=FakeStorage))
    client = EEGDBStorageClient(tmp_path / "db", library_path="native.so")

    with client:
        study_id = client.create_study(
            "test",
            [{"channel_id": 0, "label": "Cz", "sample_rate": 2, "data_type": DT_INT16}],
            {"lab": "lab-a"},
        )
        assert study_id == "101"
        assert client.is_connected
        assert client.list_studies()[0]["num_channels"] == 1
        assert client.search_studies({"lab": "lab-a"})[0]["study_id"] == "101"

        client.write_batch(study_id, 0, DT_INT16, 0, np.array([1, -2, 3], dtype=np.int16))
        start, values = client.read_batch(study_id, 0, DT_INT16, 0, 3)
        assert start == 0
        np.testing.assert_array_equal(values, [1, -2, 3])

        client.write_events_json(study_id, [Event(onset=100, type="marker", code="A")])
        assert client.read_events(study_id)[0].code == "A"
        client.flush_study(study_id)

    assert not client.is_connected

