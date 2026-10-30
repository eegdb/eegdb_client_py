import numpy as np

from eegdb_client.analysis import EEGDBTrials, iter_signal_chunks


class ChunkClient:
    def __init__(self):
        self.calls = []

    def get_study(self, study_id):
        return {"end_index": 5}

    def query_channels(
        self, study_id, channel_ids, *, idx_start, idx_end, physical, references
    ):
        self.calls.append((idx_start, idx_end))
        return {
            "channels": [
                {
                    "channel_id": channel_id,
                    "unit": "uV",
                    "samples": list(range(idx_start + channel_id, idx_end + channel_id)),
                }
                for channel_id in channel_ids
            ]
        }

    def query_trials(self, study_id, **filters):
        return {
            "study_id": study_id,
            "trials": [{"trial_id": "t1", "condition": "target", "correct": True}],
        }


def test_iter_signal_chunks_reads_aligned_bounded_ranges():
    client = ChunkClient()

    chunks = list(iter_signal_chunks(client, "s1", [0, 1], chunk_samples=2))

    assert client.calls == [(0, 2), (2, 4), (4, 5)]
    assert [(chunk.start_index, chunk.end_index) for chunk in chunks] == [
        (0, 2),
        (2, 4),
        (4, 5),
    ]
    np.testing.assert_array_equal(chunks[0].data, [[0, 1], [1, 2]])
    frame = chunks[0].to_pandas()
    assert frame.index.tolist() == [0, 1]
    assert frame.columns.tolist() == ["ch_0", "ch_1"]


def test_trials_container_converts_to_dataframe():
    trials = EEGDBTrials.from_server(ChunkClient(), "s1", condition="target")

    assert len(trials) == 1
    assert trials.to_pandas().loc[0, "trial_id"] == "t1"
