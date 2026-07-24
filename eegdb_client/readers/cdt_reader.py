"""Read Curry CDT files via MNE into SourceFile."""

from __future__ import annotations

import mne

from .mne_common import raw_to_source_file
from ..models import SourceFile


def read_cdt(path: str) -> SourceFile:
    """Load a Curry recording (.cdt / companion .ceo/.dap/.rs3/.rs4).

    Requires the ``curryreader`` package (MNE >= 1.11).
    """
    try:
        raw = mne.io.read_raw_curry(path, preload=True, verbose=False)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Curry/CDT support requires the curryreader package. "
            "Install with: pip install curryreader"
        ) from exc
    return raw_to_source_file(raw, path, "cdt")
