#!/usr/bin/env python3
"""Minimal PyTorch Dataset over the EEGDB HTTP API demo client."""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Iterator, Optional, Tuple

import numpy as np

try:
    import torch
    from torch.utils.data import DataLoader, Dataset
except ImportError as exc:
    raise SystemExit("Install PyTorch first: pip install torch") from exc

THIS_DIR = pathlib.Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from http_api_demo import EEGDBClient  # noqa: E402


class EEGChunkDataset(Dataset):
    """Sliding-window dataset over one EEG channel."""

    def __init__(
        self,
        client: EEGDBClient,
        study_id: str,
        channel_id: int,
        window_samples: int,
        stride: int,
        physical: bool = True,
        max_windows: Optional[int] = None,
    ) -> None:
        self.client = client
        self.study_id = study_id
        self.channel_id = channel_id
        self.window = window_samples
        self.stride = stride
        self.physical = physical

        study = client.get_study(study_id)
        channel = next(c for c in study["channels"] if c["channel_id"] == channel_id)
        self.sample_rate = float(channel.get("sample_rate", 256))

        meta = client.query_channel(study_id, channel_id, idx_start=0, idx_end=0)
        self.total_samples = int(meta.get("sample_count", 0))
        if self.total_samples < window_samples:
            raise ValueError(
                f"channel has {self.total_samples} samples, need at least {window_samples}"
            )

        total_windows = 1 + (self.total_samples - window_samples) // stride
        self.num_windows = (
            total_windows if max_windows is None else min(total_windows, max_windows)
        )

    def __len__(self) -> int:
        return self.num_windows

    def __getitem__(self, index: int) -> Tuple[torch.Tensor, float]:
        if index < 0 or index >= self.num_windows:
            raise IndexError(index)

        start = index * self.stride
        end = start + self.window - 1
        payload = self.client.query_channel(
            self.study_id,
            self.channel_id,
            idx_start=start,
            idx_end=end,
        )
        key = "physical_values" if self.physical else "values"
        values = payload.get(key) or payload.get("values") or []
        tensor = torch.from_numpy(np.asarray(values, dtype=np.float32))
        return tensor, self.sample_rate


def iter_batches(
    client: EEGDBClient,
    study_id: str,
    channel_id: int,
    window_samples: int,
    stride: int,
    batch_size: int = 4,
) -> Iterator[torch.Tensor]:
    """Convenience DataLoader wrapper."""

    dataset = EEGChunkDataset(client, study_id, channel_id, window_samples, stride)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    for batch, _ in loader:
        yield batch


def main() -> None:
    parser = argparse.ArgumentParser(description="EEGDB PyTorch chunk demo")
    parser.add_argument("--server", default="http://localhost:8080")
    parser.add_argument("--study-id", required=True)
    parser.add_argument("--channel", type=int, default=0)
    parser.add_argument("--window", type=int, default=512)
    parser.add_argument("--stride", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--token-name", default="")
    parser.add_argument("--api-token", default="")
    args = parser.parse_args()

    client = EEGDBClient(args.server, token_name=args.token_name, api_token=args.api_token)
    dataset = EEGChunkDataset(
        client,
        args.study_id,
        args.channel,
        args.window,
        args.stride,
        max_windows=8,
    )
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False)
    for index, (batch, rate) in enumerate(loader):
        print(f"batch {index}: shape={tuple(batch.shape)} sample_rate={rate[0].item():.1f} Hz")


if __name__ == "__main__":
    main()
