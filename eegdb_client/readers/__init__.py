from __future__ import annotations

import os

from .cdt_reader import read_cdt
from .edf_reader import read_edf
from .fif_reader import read_fif
from ..models import SourceFile

__all__ = ["read_cdt", "read_edf", "read_fif", "load_source_file"]

_CURRY_EXTS = {".cdt", ".ceo", ".dap", ".rs3", ".rs4"}


def load_source_file(path: str) -> SourceFile:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fif":
        return read_fif(path)
    if ext in (".edf", ".bdf"):
        return read_edf(path)
    if ext in _CURRY_EXTS:
        return read_cdt(path)
    raise ValueError(f"unsupported file type: {ext}")
