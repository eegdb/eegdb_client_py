"""Read EDF/BDF files into SourceFile."""

from __future__ import annotations

import os

import numpy as np
import pyedflib

from ..models import DT_INT16, ChannelDef, SourceFile


def read_edf(path: str) -> SourceFile:
    f = pyedflib.EdfReader(path)
    try:
        n_signals = f.signals_in_file
        channels: list[ChannelDef] = []
        channel_data: dict[int, np.ndarray] = {}

        for i in range(n_signals):
            dig_min = f.getDigitalMinimum(i)
            dig_max = f.getDigitalMaximum(i)
            phys_min = f.getPhysicalMinimum(i)
            phys_max = f.getPhysicalMaximum(i)
            scale = 1.0
            offset = 0.0
            if dig_max != dig_min:
                scale = (phys_max - phys_min) / (dig_max - dig_min)
                offset = phys_min - scale * dig_min

            ch = ChannelDef(
                label=f.getLabel(i).strip(),
                channel_id=i,
                sample_rate=f.getSampleFrequency(i),
                data_type=DT_INT16,
                unit=f.getPhysicalDimension(i).strip() or "uV",
                physical_min=phys_min,
                physical_max=phys_max,
                digital_min=dig_min,
                digital_max=dig_max,
                scale_factor=scale,
                offset=offset,
                transducer=f.getTransducer(i).strip(),
                prefilter=f.getPrefilter(i).strip(),
                samples_per_record=int(f.getNSamples()[i]),
            )
            channels.append(ch)
            physical = f.readSignal(i)
            if dig_max != dig_min:
                digital = np.clip(
                    ((physical - phys_min) / (phys_max - phys_min) * (dig_max - dig_min) + dig_min),
                    dig_min,
                    dig_max,
                ).astype(np.int16)
            else:
                digital = np.zeros(len(physical), dtype=np.int16)
            channel_data[i] = digital

        fmt = "bdf" if f.filetype in (pyedflib.FILETYPE_BDF, pyedflib.FILETYPE_BDFPLUS) else "edf"
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
