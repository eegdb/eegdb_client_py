import json

from eegdb_client import EEGDBQueryClient
from eegdb_client.query_client import encode_params


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_encode_params_skips_empty_and_joins_lists():
    assert encode_params({"channels": [0, 1], "physical": True, "empty": "", "none": None}) == (
        "channels=0%2C1&physical=true"
    )


def test_query_client_builds_get_request(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append((req, timeout))
        return FakeResponse({"ok": True})

    monkeypatch.setattr("eegdb_client.query_client.urlopen", fake_urlopen)

    client = EEGDBQueryClient("http://localhost:8080/", timeout=3)
    resp = client.query_psd("s1", channels=[0, 1], idx_start=0, idx_end=1000)

    assert resp == {"ok": True}
    req, timeout = calls[0]
    assert timeout == 3
    assert req.get_method() == "GET"
    assert req.full_url == "http://localhost:8080/api/v1/studies/s1/psd?channels=0%2C1&idx_start=0&idx_end=1000"


def test_query_client_builds_post_json_request(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append((req, timeout))
        return FakeResponse({"job_id": "quality_scan-1"})

    monkeypatch.setattr("eegdb_client.query_client.urlopen", fake_urlopen)

    client = EEGDBQueryClient("http://localhost:8080")
    resp = client.submit_job("quality_scan", study_id="s1", detector_options={"window_samples": 64})

    assert resp == {"job_id": "quality_scan-1"}
    req, _ = calls[0]
    assert req.get_method() == "POST"
    assert req.full_url == "http://localhost:8080/api/v1/admin/jobs"
    assert req.headers["Content-type"] == "application/json"
    assert json.loads(req.data.decode("utf-8")) == {
        "type": "quality_scan",
        "study_id": "s1",
        "detector_options": {"window_samples": 64},
    }


def test_query_client_quality_scan_async_path(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req)
        return FakeResponse({"type": "quality_scan"})

    monkeypatch.setattr("eegdb_client.query_client.urlopen", fake_urlopen)

    client = EEGDBQueryClient("http://localhost:8080")
    resp = client.scan_quality("s1", detector_options={"line_frequency": 60}, async_job=True)

    assert resp == {"type": "quality_scan"}
    req = calls[0]
    assert req.full_url == "http://localhost:8080/api/v1/studies/s1/quality/scan?async=true"
    assert json.loads(req.data.decode("utf-8")) == {"line_frequency": 60}
