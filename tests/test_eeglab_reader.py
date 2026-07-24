from eegdb_client.readers.eeglab_reader import normalize_eeglab_event


def test_normalize_eeglab_numeric_events_as_stimulus():
    event_type, code, attrs = normalize_eeglab_event("12")

    assert event_type == "stimulus"
    assert code == "12"
    assert attrs["eeglab_event"] == "12"


def test_normalize_eeglab_boundary_as_marker():
    event_type, code, _ = normalize_eeglab_event("boundary")

    assert event_type == "marker"
    assert code == "boundary"


def test_normalize_eeglab_artifact_events():
    event_type, code, _ = normalize_eeglab_event("reject eye blink")

    assert event_type == "artifact"
    assert code == "reject_eye_blink"


def test_normalize_eeglab_prefixed_response():
    event_type, code, _ = normalize_eeglab_event("Response/button 1")

    assert event_type == "response"
    assert code == "button_1"
