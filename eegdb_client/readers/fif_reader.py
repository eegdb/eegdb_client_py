"""Read FIF files via MNE into SourceFile."""

from __future__ import annotations

import mne

from .mne_common import raw_to_source_file
from ..models import SourceFile


def read_fif(path: str) -> SourceFile:
    raw = mne.io.read_raw_fif(path, preload=True, verbose=False)
    return raw_to_source_file(raw, path, "fif")
