"""Trunking: extract control-channel events from decoder frame streams.

Honest scope for M5: this is a *log-stream parser + state machine*, not a
ground-up TSBK / CSBK demodulator. Real P25 LCCH and DMR CSBK decoding lives
in the underlying decoder (dsd-fme); we ingest its output and turn the line
patterns into structured ``TrunkingEvent`` records.
"""

from .schema import TrunkingEvent, TrunkingEventKind
from .p25_lccp import extract_p25_events
from .dmr_csbk import extract_dmr_events
from .annotator import annotate_channels, attach_to_report

__all__ = [
    "TrunkingEvent", "TrunkingEventKind",
    "extract_p25_events", "extract_dmr_events",
    "annotate_channels", "attach_to_report",
]
