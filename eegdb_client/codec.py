"""Compatibility imports for the standalone EEGDB native read codec."""

from __future__ import annotations

try:
    from eegdb_codec import CodecError, EEGDBCodec, find_codec_library, numpy_dtype
except ModuleNotFoundError:
    import numpy as np

    from .models import DT_FLOAT32, DT_FLOAT64, DT_INT16, DT_INT24, DT_INT64

    class CodecError(RuntimeError):
        pass

    class EEGDBCodec:
        def __init__(self, *args: object, **kwargs: object):
            raise CodecError(
                "EEGDB local decode requires the standalone eegdb-codec package. "
                "Build it from git@github.com:eegdb/eegdb-codec.git and install the wheel, "
                "or disable --local-decode."
            )

    def find_codec_library() -> str:
        return ""

    def numpy_dtype(data_type: int) -> np.dtype:
        return {
            DT_INT16: np.int16,
            DT_INT24: np.int32,
            DT_FLOAT32: np.float32,
            DT_FLOAT64: np.float64,
            DT_INT64: np.int64,
        }[data_type]


__all__ = ["CodecError", "EEGDBCodec", "find_codec_library", "numpy_dtype"]
