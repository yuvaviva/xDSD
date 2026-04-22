"""P25 encryption probe.

Consumes the FrameRecord list produced by a P25-capable adapter (typically
``dsd_fme``) and aggregates algid / keyid / NAC into a single
``EncryptionFinding``.
"""

from __future__ import annotations

from typing import Iterable, List

from .schema import EncryptionFinding, P25_ALG


def probe_p25_frames(frames: Iterable[dict]) -> EncryptionFinding:
    first_algid = None
    first_keyid = None
    evidence: List[str] = []
    for fr in frames:
        if (alg := fr.get("algid")) is not None:
            if first_algid is None:
                first_algid = int(alg)
                evidence.append(f"algid=0x{int(alg):02X}")
        if (key := fr.get("keyid")) is not None and first_keyid is None:
            first_keyid = int(key)
            evidence.append(f"keyid=0x{int(key):04X}")
        if fr.get("type") == "ENCRYPTION_EVIDENCE":
            line = fr.get("log_line")
            if line:
                evidence.append(line)
    if first_algid is None:
        return EncryptionFinding(encrypted=False,
                                 evidence=["no P25 HDU/algid observed"])
    name = P25_ALG.get(first_algid, f"UNKNOWN(0x{first_algid:02X})")
    is_clear = first_algid == 0x80
    return EncryptionFinding(
        encrypted=not is_clear,
        algorithm=None if is_clear else name,
        algorithm_id=first_algid,
        key_id=first_keyid,
        evidence=evidence or [f"algid=0x{first_algid:02X}"],
    )
