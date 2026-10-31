import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from eegdb_client.ui.event_dialog import EventEditDialog


def test_event_dialog_round_trip():
    app = QApplication.instance() or QApplication([])
    dialog = EventEditDialog(
        [
            {
                "event_id": "event-1",
                "type": "stimulus",
                "onset_us": 123,
                "duration_us": 4,
                "channel_id": 65535,
                "code": "S1",
                "description": "target",
                "trial_id": "trial-1",
                "source": "bids",
                "confidence": 0.9,
                "attributes": {"condition": "rare"},
            }
        ]
    )

    events = dialog.events()
    assert len(events) == 1
    assert events[0]["event_id"] == "event-1"
    assert events[0]["onset_us"] == 123
    assert events[0]["attributes"] == {"condition": "rare"}
    dialog.close()
    app.processEvents()
