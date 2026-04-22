"""Trunking event dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Literal, Optional


TrunkingEventKind = Literal[
    "grant", "update", "release", "registration", "info",
]


@dataclass
class TrunkingEvent:
    kind: TrunkingEventKind
    protocol: str                      # "p25" | "dmr"
    t_offset_s: float                  # within the source channel's timeline
    source_event_id: str               # the channel from which this was lifted
    talkgroup_id: Optional[int] = None
    source_id: Optional[int] = None    # subscriber / radio id
    grant_freq_hz: Optional[float] = None
    lcn: Optional[int] = None
    pdu: Optional[int] = None
    nac: Optional[int] = None
    raw: Optional[str] = None          # log line for traceability

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
