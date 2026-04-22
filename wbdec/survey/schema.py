"""SurveyEvent / SurveyResult dataclasses — the M1 output schema."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Literal, Optional


SurveyKind = Literal["continuous", "burst"]


@dataclass
class SurveyEvent:
    event_id: str                 # stable id, e.g. "ev_000042"
    center_hz: float              # absolute RF frequency
    bw_hz: float
    t_start_s: float              # seconds since capture start
    t_end_s: float
    kind: SurveyKind              # "continuous" or "burst"
    snr_db: float
    peak_power_db: float
    hits: int                     # frames this track was active
    duty_cycle: float             # burst-tracker occupancy within its window
    label: Optional[str] = None
    label_confidence: float = 0.0
    features: Optional[Dict[str, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SurveyResult:
    capture_meta_path: str
    sample_rate_hz: float
    center_hz: float
    duration_s: float
    num_frames: int
    frame_period_s: float
    events: List[SurveyEvent] = field(default_factory=list)
    gaps: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capture_meta_path": self.capture_meta_path,
            "sample_rate_hz":    self.sample_rate_hz,
            "center_hz":         self.center_hz,
            "duration_s":        self.duration_s,
            "num_frames":        self.num_frames,
            "frame_period_s":    self.frame_period_s,
            "events":            [e.to_dict() for e in self.events],
            "gaps":              self.gaps,
        }

    def write_json(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as fh:
            json.dump(self.to_dict(), fh, indent=2, default=_json_default)


def _json_default(o: Any) -> Any:
    try:
        import numpy as np  # noqa: F401
        if hasattr(o, "item"):
            return o.item()
    except Exception:
        pass
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")
