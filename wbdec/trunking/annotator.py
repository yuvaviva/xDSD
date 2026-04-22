"""Match TrunkingEvents to extracted channels and enrich the report.

Two effects:

1. **Per-channel annotations**: each ``ChannelReport`` for a channel that
   carried trunking traffic gets ``talkgroup_id`` / ``source_id`` set if at
   least one update/grant was observed during that channel's time window.
2. **Predictive matching**: a ``grant`` event with a freq announces a
   future voice channel; we attach the talkgroup id to any later channel
   whose center matches the grant within ``freq_tol_hz`` and whose
   ``t_start_s`` falls in ``[grant_t, grant_t + window_s]``.
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

from ..encryption.aggregator import load_frames_jsonl
from .dmr_csbk import extract_dmr_events
from .p25_lccp import extract_p25_events
from .schema import TrunkingEvent


def _events_for_channel(channel) -> List[TrunkingEvent]:
    """Run the protocol-appropriate trunking extractor on a channel's frames.

    If the classifier missed (e.g. labelled a real P25 carrier as "dpmr") we
    still run the parsers as long as the frames stream contains TRUNKING_*
    rows — the parsers themselves are protocol-agnostic for the fields they
    care about (TG/SRC/LCN/grant_freq/PDU). DMR is the fallback only when
    the channel was explicitly labelled DMR; everything else (including
    "unknown") routes through the P25 parser.
    """
    if channel.frames_jsonl_path is None:
        return []
    frames = load_frames_jsonl(channel.frames_jsonl_path)
    if not frames:
        return []
    has_trunking = any(
        f.get("type") in ("TRUNKING_GRANT", "TRUNKING_INFO") for f in frames)
    if not has_trunking and channel.label not in ("p25_c4fm", "dmr"):
        return []
    if channel.label == "dmr":
        return extract_dmr_events(channel.event_id, channel.nac, frames)
    return extract_p25_events(channel.event_id, channel.nac, frames)


def _absolute_time(channel, t_offset_s: float) -> float:
    return channel.t_start_s + t_offset_s


def annotate_channels(channels, freq_tol_hz: float = 6_250.0,
                      grant_window_s: float = 30.0) -> List[TrunkingEvent]:
    """Walk the channels twice: pass 1 collects events; pass 2 applies them.

    Returns the full list of TrunkingEvents (sorted by absolute time) for
    inclusion in the report.
    """
    all_events: List[Tuple[float, TrunkingEvent]] = []
    for c in channels:
        evs = _events_for_channel(c)
        # First pass: per-source-channel annotations.
        for e in evs:
            if e.kind in ("update", "grant") and (
                    e.talkgroup_id is not None or e.source_id is not None):
                if c.talkgroup_id is None and e.talkgroup_id is not None:
                    c.talkgroup_id = e.talkgroup_id
                if c.source_id is None and e.source_id is not None:
                    c.source_id = e.source_id
            all_events.append((_absolute_time(c, e.t_offset_s), e))

    # Second pass: grants → match later channels that look like the granted
    # voice channel (freq match, time within grant_window_s).
    grants = [(t, e) for t, e in all_events
              if e.kind == "grant" and e.grant_freq_hz is not None]
    for c in channels:
        if c.talkgroup_id is not None:
            continue
        for grant_t, g in grants:
            if abs(c.center_hz - g.grant_freq_hz) > freq_tol_hz:
                continue
            if not (grant_t <= c.t_start_s <= grant_t + grant_window_s):
                continue
            c.talkgroup_id = g.talkgroup_id
            c.source_id = g.source_id
            c.granted_by_event_id = g.source_event_id
            break

    all_events.sort(key=lambda pair: pair[0])
    return [e for _, e in all_events]


def attach_to_report(report, freq_tol_hz: float = 6_250.0,
                     grant_window_s: float = 30.0) -> None:
    """Mutate ``report.channels`` in place and attach ``report.trunking_events``.

    Channels gain optional ``talkgroup_id``, ``source_id`` and
    ``granted_by_event_id`` attributes — set when annotation succeeded.
    """
    for c in report.channels:
        # Ensure attributes exist regardless of annotation outcome.
        if not hasattr(c, "talkgroup_id"):
            c.talkgroup_id = None
        if not hasattr(c, "source_id"):
            c.source_id = None
        if not hasattr(c, "granted_by_event_id"):
            c.granted_by_event_id = None
    events = annotate_channels(
        report.channels, freq_tol_hz=freq_tol_hz,
        grant_window_s=grant_window_s,
    )
    report.trunking_events = events  # type: ignore[attr-defined]
