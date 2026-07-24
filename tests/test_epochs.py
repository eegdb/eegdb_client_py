import numpy as np

from eegdb_client.analysis import EEGDBEpochs
from eegdb_client.analysis.epochs import mne_events, unit_scale_to_volts


def test_epochs_from_response_builds_tensor_and_average():
    response = {
        "study_id": "s1",
        "pre_ms": 1,
        "post_ms": 2,
        "sample_rate": 1000,
        "channels": [0, 1],
        "epochs": [
            {
                "event": {"type": "stimulus", "code": "target", "trial_id": "t1", "onset_us": 1000},
                "channels": [
                    {"channel_id": 0, "unit": "uV", "samples": [1, 2, 3]},
                    {"channel_id": 1, "unit": "uV", "samples": [10, 20, 30]},
                ],
            },
            {
                "event": {"type": "stimulus", "code": "target", "trial_id": "t2", "onset_us": 2000},
                "channels": [
                    {"channel_id": 0, "unit": "uV", "samples": [3, 4, 5]},
                    {"channel_id": 1, "unit": "uV", "samples": [30, 40, 50]},
                ],
            },
        ],
    }

    epochs = EEGDBEpochs.from_response(response)

    assert epochs.study_id == "s1"
    assert epochs.shape == (2, 2, 3)
    assert epochs.channel_names == ["CH0", "CH1"]
    np.testing.assert_allclose(epochs.time_axis_ms, [-1, 0, 1])
    np.testing.assert_allclose(epochs.average(), [[2, 3, 4], [20, 30, 40]])
    assert epochs.metadata[0]["trial_id"] == "t1"


def test_epochs_rejects_inconsistent_sample_counts():
    response = {
        "study_id": "s1",
        "sample_rate": 1000,
        "channels": [0],
        "epochs": [
            {"channels": [{"channel_id": 0, "samples": [1, 2, 3]}]},
            {"channels": [{"channel_id": 0, "samples": [1, 2]}]},
        ],
    }

    try:
        EEGDBEpochs.from_response(response)
    except ValueError as exc:
        assert "expected 3" in str(exc)
    else:
        raise AssertionError("expected inconsistent epoch length error")


def test_mne_events_maps_codes_to_integer_ids():
    events, event_id = mne_events(
        [
            {"code": "target", "onset_us": 1000},
            {"code": "standard", "onset_us": 2000},
            {"code": "target", "onset_us": 3000},
        ],
        sample_rate=1000,
    )

    assert event_id == {"target": 1, "standard": 2}
    assert events.tolist() == [[1, 0, 1], [2, 0, 2], [3, 0, 1]]


def test_unit_scale_to_volts():
    assert unit_scale_to_volts("uV") == 1e-6
    assert unit_scale_to_volts("mV") == 1e-3
    assert unit_scale_to_volts("digital") == 1.0
