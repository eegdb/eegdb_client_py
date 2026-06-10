#!/usr/bin/env python3
"""Generate testdata/sample.fif for E2E tests."""

from __future__ import annotations

import argparse
import os

import mne
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", default="testdata/sample_eeg.fif")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    sfreq = 256.0
    duration = 5.0
    n_samples = int(sfreq * duration)
    ch_names = ["F3", "F4", "C3", "C4"]
    rng = np.random.default_rng(42)
    data = (rng.standard_normal((len(ch_names), n_samples)) * 50e-6).astype(np.float64)

    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    raw = mne.io.RawArray(data, info)
    raw.set_annotations(mne.Annotations([1.0, 3.0], [0.0, 0.5], ["stim", "resp"]))
    raw.save(args.output, overwrite=True)
    print(args.output)


if __name__ == "__main__":
    main()
