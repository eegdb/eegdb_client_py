from eegdb_client.readers.brainvision_reader import normalize_brainvision_marker


def test_normalize_brainvision_stimulus_marker():
    event_type, code, attrs = normalize_brainvision_marker("Stimulus/S  1")

    assert event_type == "stimulus"
    assert code == "S_1"
    assert attrs["brainvision_kind"] == "Stimulus"
    assert attrs["brainvision_code"] == "S  1"


def test_normalize_brainvision_response_marker():
    event_type, code, _ = normalize_brainvision_marker("Response/R 12")

    assert event_type == "response"
    assert code == "R_12"


def test_normalize_brainvision_artifact_marker():
    event_type, code, _ = normalize_brainvision_marker("Bad Interval/blink")

    assert event_type == "artifact"
    assert code == "blink"
