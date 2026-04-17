"""Signal event dataclass produced by the detector."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional


@dataclass
class SignalEvent:
    center_hz: float         # absolute RF (baseband center + offset)
    bw_hz: float
    t_start: float           # seconds since stream start
    t_end: float
    snr_db: float
    peak_power_db: float
    # Filled later by classifier / decoder:
    label: Optional[str] = None
    label_confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
