"""DMR CSBK / Tier-III control event extraction.

Same shape as the P25 path: TRUNKING_GRANT / TRUNKING_INFO frames from
dsd_fme become ``TrunkingEvent`` records of kind ``grant``/``update``/``info``.
"""

from __future__ import annotations

from typing import Iterable, List

from .schema import TrunkingEvent


def extract_dmr_events(source_event_id: str, nac_default: int | None,
                       frames: Iterable[dict]) -> List[TrunkingEvent]:
    out: List[TrunkingEvent] = []
    for fr in frames:
        ftype = fr.get("type")
        if ftype not in ("TRUNKING_GRANT", "TRUNKING_INFO"):
            continue
        t = float(fr.get("t_offset_s", 0.0))
        tg = fr.get("talkgroup_id")
        src = fr.get("source_id")
        lcn = fr.get("lcn")
        freq = fr.get("grant_freq_hz")
        pdu = fr.get("pdu")
        nac = fr.get("nac", nac_default)
        if ftype == "TRUNKING_GRANT" or freq is not None or lcn is not None:
            kind = "grant"
        elif tg is not None and src is not None:
            kind = "update"
        else:
            kind = "info"
        out.append(TrunkingEvent(
            kind=kind, protocol="dmr", t_offset_s=t,
            source_event_id=source_event_id,
            talkgroup_id=int(tg) if tg is not None else None,
            source_id=int(src) if src is not None else None,
            grant_freq_hz=float(freq) if freq is not None else None,
            lcn=int(lcn) if lcn is not None else None,
            pdu=int(pdu) if pdu is not None else None,
            nac=int(nac) if nac is not None else None,
            raw=fr.get("log_line"),
        ))
    return out
