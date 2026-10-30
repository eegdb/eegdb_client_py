from __future__ import annotations

import os

from .cdt_reader import read_cdt
from .brainvision_reader import read_brainvision
from .edf_reader import read_edf
from .eeglab_reader import read_eeglab
from .fif_reader import read_fif
from .lsl_reader import record_lsl
from .xdf_reader import read_xdf
from ..models import SourceFile

__all__ = [
    "read_brainvision",
    "read_cdt",
    "read_edf",
    "read_eeglab",
    "read_fif",
    "record_lsl",
    "read_xdf",
    "load_source_file",
]

_CURRY_EXTS = {".cdt", ".ceo", ".dap", ".rs3", ".rs4"}


def load_source_file(path: str) -> SourceFile:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fif":
        return read_fif(path)
    if ext == ".vhdr":
        return read_brainvision(path)
    if ext == ".set":
        return read_eeglab(path)
    if ext == ".xdf":
        return read_xdf(path)
    if ext in (".edf", ".bdf"):
        return read_edf(path)
    if ext in _CURRY_EXTS:
        return read_cdt(path)
    raise ValueError(f"unsupported file type: {ext}")
