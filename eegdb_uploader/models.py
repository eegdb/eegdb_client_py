from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


# Data types matching pkg/common/const.go
DT_INT16 = 0x01
DT_INT24 = 0x02
DT_FLOAT32 = 0x03
DT_FLOAT64 = 0x04
DT_INT64 = 0x05


@dataclass
class StudyAttrs:
    lab: str = ""
    pi: str = ""
    device_type: str = ""
    device_serial: str = ""
    sampling_rate: str = ""
    paradigm: str = ""
    population: str = ""
    condition: str = ""
    session: str = ""
    ethics_approval: str = ""
    custom: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if not d["custom"]:
            del d["custom"]
        return {k: v for k, v in d.items() if v}


@dataclass
class ChannelDef:
    label: str
    channel_id: int
    sample_rate: float
    data_type: int = DT_INT16
    type: str = "EEG"
    unit: str = "uV"
    physical_min: float = -32768.0
    physical_max: float = 32767.0
    digital_min: int = -32768
    digital_max: int = 32767
    scale_factor: float = 1.0
    offset: float = 0.0
    transducer: str = ""
    prefilter: str = ""
    samples_per_record: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Event:
    onset: int
    duration: int = 0
    channel_id: int = 0xFFFF
    code: str = ""
    description: str = ""


@dataclass
class SourceFile:
    path: str
    format: str  # edf | fif
    name: str
    channels: List[ChannelDef]
    events: List[Event] = field(default_factory=list)
    patient_id: str = ""
    recording_id: str = ""
    start_time: Optional[datetime] = None
    data_record_dur_sec: float = 1.0
    channel_data: Dict[int, Any] = field(default_factory=dict)


@dataclass
class StudySummary:
    study_id: str
    name: str
    num_samples: int = 0
    num_channels: int = 0
    created_at: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    source_file_format: str = ""
