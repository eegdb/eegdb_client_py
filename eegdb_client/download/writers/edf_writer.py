"""Write downloaded study data to EDF/BDF."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import numpy as np
import pyedflib

from ...models import DT_FLOAT32, DT_FLOAT64, DT_INT24, Event


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
        for ch in channels:
            if ch.get("data_type") in (DT_FLOAT32, DT_FLOAT64):
                dig_min = -32768
                dig_max = 32767
            else:
                if ch.get("data_type") == DT_INT24:
                    dig_min = int(ch.get("digital_min", -8388608))
                    dig_max = int(ch.get("digital_max", 8388607))
                else:
                    dig_min = int(ch.get("digital_min", -32768))
                    dig_max = int(ch.get("digital_max", 32767))
            phys_min = float(ch.get("physical_min", dig_min))
            phys_max = float(ch.get("physical_max", dig_max))
            if phys_max <= phys_min:
                phys_min, phys_max = -1.0, 1.0

            sr = float(ch.get("sample_rate", 256.0))
            spr = int(ch.get("samples_per_record") or 0) or max(1, int(round(sr)))
            headers.append(
                {
                    "label": str(ch.get("label", ""))[:16],
                    "dimension": str(ch.get("unit", "uV"))[:8],
                    "sample_frequency": spr,
                    "physical_min": phys_min,
                    "physical_max": phys_max,
                    "digital_min": dig_min,
                    "digital_max": dig_max,
                    "transducer": str(ch.get("transducer", ""))[:80],
                    "prefilter": str(ch.get("prefilter", ""))[:80],
                }
            )

        writer.setSignalHeaders(headers)
        record_count = max(
            (len(channel_data[ch["channel_id"]]) + headers[i]["sample_frequency"] - 1)
            // headers[i]["sample_frequency"]
            for i, ch in enumerate(channels)
        )
        for record in range(record_count):
            record_parts = []
            for i, ch in enumerate(channels):
                arr = channel_data[ch["channel_id"]]
                spr = headers[i]["sample_frequency"]
                start_idx, end_idx = record * spr, min((record + 1) * spr, len(arr))
                raw = np.asarray(arr[start_idx:end_idx])
                if ch.get("data_type") in (DT_FLOAT32, DT_FLOAT64):
                    physical = raw.astype(np.float64)
                else:
                    dig_min, dig_max = headers[i]["digital_min"], headers[i]["digital_max"]
                    phys_min, phys_max = headers[i]["physical_min"], headers[i]["physical_max"]
                    scale = (phys_max - phys_min) / (dig_max - dig_min) if dig_max != dig_min else 1.0
                    physical = raw.astype(np.float64) * scale + (phys_min - scale * dig_min)
                if len(physical) < spr:
                    physical = np.pad(physical, (0, spr - len(physical)))
                record_parts.append(physical)
            writer.blockWritePhysicalSamples(np.concatenate(record_parts))

        for e in events:
            writer.writeAnnotation(e.onset / 1_000_000.0, e.duration / 1_000_000.0, e.description or e.code)
    finally:
        writer.close()
