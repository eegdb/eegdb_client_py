"""Read EDF/BDF files into SourceFile."""

from __future__ import annotations

import os

import numpy as np
import pyedflib

from ..models import DT_INT16, DT_INT24, ChannelDef, SourceFile


def read_edf(path: str) -> SourceFile:
    f = pyedflib.EdfReader(path)
    try:
        is_bdf = f.filetype in (pyedflib.FILETYPE_BDF, pyedflib.FILETYPE_BDFPLUS)
        data_type = DT_INT24 if is_bdf else DT_INT16
        n_signals = f.signals_in_file
        channels: list[ChannelDef] = []
        channel_data: dict[int, np.ndarray] = {}

        for i in range(n_signals):
            dig_min = int(f.getDigitalMinimum(i))
            dig_max = int(f.getDigitalMaximum(i))
            phys_min = float(f.getPhysicalMinimum(i))
            phys_max = float(f.getPhysicalMaximum(i))
            scale = 1.0
            offset = 0.0
            if dig_max != dig_min:
                scale = (phys_max - phys_min) / (dig_max - dig_min)
                offset = phys_min - scale * dig_min

            spr = int(f.smp_per_record(i))
            ch = ChannelDef(
                label=f.getLabel(i).strip(),
                channel_id=i,
                sample_rate=float(f.getSampleFrequency(i)),
                data_type=data_type,
                unit=f.getPhysicalDimension(i).strip() or "uV",
                physical_min=phys_min,
                physical_max=phys_max,
                digital_min=dig_min,
                digital_max=dig_max,
                scale_factor=scale,
                offset=offset,
                transducer=f.getTransducer(i).strip(),
                prefilter=f.getPrefilter(i).strip(),
                samples_per_record=spr,
            )
            channels.append(ch)
            channel_data[i] = _read_digital(f, i, data_type)

        fmt = "bdf" if is_bdf else "edf"
        return SourceFile(
            path=path,
            format=fmt,
            name=os.path.splitext(os.path.basename(path))[0],
            channels=channels,
            patient_id=f.getPatientCode().strip(),
            recording_id=f.getRecordingAdditional().strip(),
            start_time=f.getStartdatetime(),
            data_record_dur_sec=float(f.datarecord_duration),
            channel_data=channel_data,
        )
    finally:
        f.close()


def _read_digital(f: pyedflib.EdfReader, signal_idx: int, data_type: int) -> np.ndarray:
    n = int(f.getNSamples()[signal_idx])
    buf = np.zeros(n, dtype=np.int32)
    f.read_digital_signal(signal_idx, 0, n, buf)
    if data_type == DT_INT16:
        return buf.astype(np.int16)
    return buf
