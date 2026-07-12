"""Local decode helpers for eegdb-codec (current pkg/wire + C ABI).

TCP ReadCompressedBatch returns (algo, compressed_payload). Decoding uses the
eegdb_codec Python package (ctypes over libeegdbcodec), which mirrors
pkg/codec.DecodeRaw.

BlockCodec IDs on the wire match Go internal/codec/block.BlockCodec:
  0=lz4, 1=zstd, 2=flac, 3=wavpack, 4=best
"""

from __future__ import annotations

from typing import Optional

import numpy as np

# Wire BlockCodec enum (must stay in sync with eegdb-codec / EEGDB TCP).
BLOCK_CODEC_LZ4 = 0
BLOCK_CODEC_ZSTD = 1
BLOCK_CODEC_FLAC = 2
BLOCK_CODEC_WAVPACK = 3
BLOCK_CODEC_BEST = 4

_BLOCK_CODEC_BY_NAME = {
    "lz4": BLOCK_CODEC_LZ4,
    "zstd": BLOCK_CODEC_ZSTD,
    "flac": BLOCK_CODEC_FLAC,
    "wavpack": BLOCK_CODEC_WAVPACK,
    "best": BLOCK_CODEC_BEST,
    "": BLOCK_CODEC_BEST,
}


def parse_block_codec(name: str) -> int:
    key = (name or "best").strip().lower()
    if key not in _BLOCK_CODEC_BY_NAME:
        raise ValueError(f"unknown block codec {name!r} (want lz4|zstd|flac|wavpack|best)")
    return _BLOCK_CODEC_BY_NAME[key]


def block_codec_name(codec_id: int) -> str:
    for name, cid in _BLOCK_CODEC_BY_NAME.items():
        if name and cid == codec_id:
            return name
    return f"unknown({codec_id})"


class LocalCodec:
    """Thin wrapper around eegdb_codec.EEGDBCodec."""

    def __init__(self, library_path: Optional[str] = None):
        try:
            from eegdb_codec import EEGDBCodec, CodecError  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "eegdb_codec is required for --local-decode. Build and install it:\n"
                "  cd /path/to/eegdb-codec && make codec-wheel\n"
                "  pip install dist/python/eegdb_codec-*.whl\n"
                "Or set EEGDB_CODEC_LIB to libeegdbcodec.so and pip install -e "
                "eegdb-codec/python"
            ) from exc
        self._CodecError = CodecError
        self._codec = EEGDBCodec(library_path)

    @property
    def version(self) -> int:
        return self._codec.version()

    def supports(self, data_type: int, algo: int) -> bool:
        return self._codec.supports(data_type, algo)

    def decode(self, data_type: int, algo: int, sample_count: int, payload: bytes) -> np.ndarray:
        try:
            return self._codec.decode(data_type, algo, sample_count, payload)
        except self._CodecError as exc:
            raise RuntimeError(str(exc)) from exc
