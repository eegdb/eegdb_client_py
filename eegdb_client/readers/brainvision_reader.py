"""Read BrainVision recordings through MNE."""

from __future__ import annotations

import mne

from ..models import SourceFile
from .mne_common import raw_to_source_file


def read_brainvision(path: str) -> SourceFile:
    raw = mne.io.read_raw_brainvision(path, preload=False, verbose=False)
    return raw_to_source_file(raw, path, "brainvision")
