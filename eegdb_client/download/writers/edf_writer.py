"""Write downloaded study data to EDF/BDF."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import numpy as np
import pyedflib

from ...models import DT_FLOAT32, Event


def write_edf_from_study(
    output_path: str,
    study: Dict[str, Any],
    channel_data: Dict[int, np.ndarray],
    events: List[Event],
    file_type: str = "edf",
) -> None:
    channels = study.get("channels", [])
    n = len(channels)
    if n == 0:
        raise ValueError("no channels")

    ftype = pyedflib.FILETYPE_BDFPLUS if file_type == "bdf" else pyedflib.FILETYPE_EDFPLUS
    writer = pyedflib.EdfWriter(output_path, n_channels=n, file_type=ftype)
    try:
        start = study.get("record_start_time")
        if isinstance(start, str):
            start = datetime.fromisoformat(start.replace("Z", "+00:00"))
        writer.setHeader(
            {
                "technician": "",
                "recording_additional": study.get("name", ""),
                "patientname": "",
                "patient_additional": "",
                "patientcode": study.get("patient_id", ""),
                "equipment": "",
                "admincode": "",
                "gender": "",
                "sex": "",
                "startdate": start or datetime.now(),
                "birthdate": "",
            }
        )

        headers = []
        buffers = []
        for ch in channels:
            ch_id = ch["channel_id"]
            arr = channel_data[ch_id]
            if ch.get("data_type") == DT_FLOAT32:
                phys = arr.astype(np.float64)
            else:
                dig_min = ch.get("digital_min", -32768)
                dig_max = ch.get("digital_max", 32767)
                phys_min = ch.get("physical_min", -32768.0)
                phys_max = ch.get("physical_max", 32767.0)
                scale = (phys_max - phys_min) / (dig_max - dig_min) if dig_max != dig_min else 1.0
                offset = phys_min - scale * dig_min
                phys = arr.astype(np.float64) * scale + offset

            sr = ch.get("sample_rate", 256.0)
            spr = max(1, int(round(sr)))
            headers.append(
                {
                    "label": str(ch.get("label", ""))[:16],
                    "dimension": str(ch.get("unit", "uV"))[:8],
                    "sample_frequency": spr,
                    "physical_min": float(np.min(phys)),
                    "physical_max": float(np.max(phys)),
                    "digital_min": ch.get("digital_min", -32768),
                    "digital_max": ch.get("digital_max", 32767),
                    "transducer": str(ch.get("transducer", ""))[:80],
                    "prefilter": str(ch.get("prefilter", ""))[:80],
                }
            )
            buffers.append(phys)

        writer.setSignalHeaders(headers)
        writer.writeSamples(buffers)

        for e in events:
            writer.writeAnnotation(e.onset / 1_000_000.0, e.duration / 1_000_000.0, e.description or e.code)
    finally:
        writer.close()
