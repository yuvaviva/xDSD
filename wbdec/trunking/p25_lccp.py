"""P25 LCCH (Trunking Single-Block) event extraction.

Operates on FrameRecord dicts produced by the dsd_fme adapter. We classify
each TRUNKING_GRANT / TRUNKING_INFO frame as a ``TrunkingEvent`` of kind
``grant`` (when a freq or LCN is present) or ``info`` otherwise.

P25 trunking signalling is opaque to us in this layer — we trust dsd-fme's
log decoding for fields like talkgroup, source, NAC. PDU ids surface in the
``pdu`` field for downstream consumers that care about TSBK type.
"""

from __future__ import annotations

from typing import Iterable, List

from .schema import TrunkingEvent


_GRANT_PDU = {
    # PDU IDs from TIA-102.AABF that announce a voice channel grant.
    0x40, 0x41, 0x42, 0x44, 0x46, 0x48, 0x49, 0x4A, 0x4C,
}


def extract_p25_events(source_event_id: str, nac_default: int | None,
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
        kind: str = "info"
        if ftype == "TRUNKING_GRANT" or freq is not None or pdu in _GRANT_PDU:
            kind = "grant"
        elif tg is not None and src is not None:
            kind = "update"
        out.append(TrunkingEvent(
            kind=kind, protocol="p25", t_offset_s=t,
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
