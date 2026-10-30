from __future__ import annotations

from pathlib import Path

import numpy as np

from eegdb_client.download.fetcher import _download_channel_to_disk
from eegdb_client.models import DT_INT16, ChannelDef, SourceFile
from eegdb_client.upload.pipeline import upload_source_file
from eegdb_client.upload.checkpoint import UploadCheckpoint


class UploadClient:
    def __init__(self) -> None:
        self.writes: list[tuple[int, int, np.ndarray]] = []

    def create_study(self, *args, **kwargs):
        return "study-1"

    def write_batch(self, study_id, channel_id, data_type, start, values):
        self.writes.append((channel_id, start, np.asarray(values).copy()))

    def flush_study(self, study_id):
        return None

    def read_events(self, study_id):
        return []

    def write_events_json(self, study_id, events):
        return None


class DownloadClient:
    @staticmethod
    def _numpy_dtype(data_type):
        return np.int16

    def __init__(self) -> None:
        self.requests: list[tuple[int, int]] = []

    def read_batch(self, study_id, channel_id, data_type, start, count):
        self.requests.append((start, count))
        return start, np.arange(start, start + count, dtype=np.int16)


def test_upload_reads_source_in_bounded_windows_and_closes_it():
    reads: list[tuple[int, int, int]] = []
    closed: list[bool] = []

    def read(channel_id: int, start: int, stop: int) -> np.ndarray:
        reads.append((channel_id, start, stop))
        return np.arange(start, stop, dtype=np.int16)

    source = SourceFile(
        path="recording.edf",
        format="edf",
        name="recording",
        channels=[ChannelDef("Cz", 0, 2, DT_INT16)],
        channel_lengths={0: 5},
        channel_reader=read,
        close_callback=lambda: closed.append(True),
    )
    client = UploadClient()

    assert upload_source_file(client, source, batch_seconds=1, resume=False) == "study-1"
    assert reads == [(0, 0, 2), (0, 2, 4), (0, 4, 5)]
    assert [start for _, start, _ in client.writes] == [0, 2, 4]
    assert closed == [True]


def test_download_writes_batches_to_disk_backed_array(tmp_path: Path):
    client = DownloadClient()
    values = _download_channel_to_disk(
        client,
        "study-1",
        0,
        DT_INT16,
        10,
        4,
        str(tmp_path / "channel.bin"),
        local_decode=False,
        block_codec=0,
        codec=None,
    )

    assert isinstance(values.base, np.memmap)
    assert client.requests == [(0, 4), (4, 4), (8, 2)]
    np.testing.assert_array_equal(values, np.arange(10, dtype=np.int16))


def test_upload_aligns_mixed_sample_rates_by_duration():
    source = SourceFile(
        path="mixed.edf",
        format="edf",
        name="mixed",
        channels=[
            ChannelDef("slow", 0, 2, DT_INT16),
            ChannelDef("fast", 1, 4, DT_INT16),
        ],
        channel_data={
            0: np.arange(4, dtype=np.int16),
            1: np.arange(8, dtype=np.int16),
        },
    )
    client = UploadClient()

    upload_source_file(client, source, batch_seconds=1, resume=False)

    fast_writes = [(start, len(values)) for ch, start, values in client.writes if ch == 1]
    assert fast_writes == [(0, 4), (4, 4)]


def test_upload_resumes_after_last_complete_window(tmp_path: Path):
    source_path = tmp_path / "recording.edf"
    source_path.write_bytes(b"fixture")
    checkpoint_path = tmp_path / "upload.json"

    class InterruptedClient(UploadClient):
        host = "localhost"
        port = 8081
        database = "default"

        def write_batch(self, study_id, channel_id, data_type, start, values):
            if start == 2:
                raise ConnectionError("interrupted")
            super().write_batch(study_id, channel_id, data_type, start, values)

    def make_source() -> SourceFile:
        return SourceFile(
            path=str(source_path),
            format="edf",
            name="recording",
            channels=[ChannelDef("Cz", 0, 2, DT_INT16)],
            channel_data={0: np.arange(5, dtype=np.int16)},
        )

    first = InterruptedClient()
    try:
        upload_source_file(
            first,
            make_source(),
            batch_seconds=1,
            checkpoint_path=checkpoint_path,
        )
    except ConnectionError:
        pass
    else:
        raise AssertionError("expected interrupted upload")

    checkpoint = UploadCheckpoint.load(checkpoint_path)
    assert checkpoint.study_id == "study-1"
    assert checkpoint.next_window_start == 2

    class ResumedClient(UploadClient):
        host = "localhost"
        port = 8081
        database = "default"

        def get_study(self, study_id):
            assert study_id == "study-1"
            return {"study_id": study_id}

    resumed = ResumedClient()
    study_id = upload_source_file(
        resumed,
        make_source(),
        batch_seconds=1,
        checkpoint_path=checkpoint_path,
    )

    assert study_id == "study-1"
    assert [start for _, start, _ in resumed.writes] == [2, 4]
    assert not checkpoint_path.exists()
