"""DMR encryption probe.

Two signal paths:

1. ``PI header`` lines — Privacy Indicator header containing ``alg`` and
   ``keyid`` fields. Upstream dsd-fme sometimes surfaces these directly.
2. ``algid`` / ``keyid`` fields reported by the adapter on voice frames.

Anything resembling encryption evidence counts; we aggregate conservatively.
"""

from __future__ import annotations

import re
from typing import Iterable, List

from .schema import DMR_ALG, EncryptionFinding


_PI_LINE = re.compile(r"(?i)PI header.*alg\s*=?\s*0x([0-9a-f]+)"
                      r"(?:.*key\s*id\s*=?\s*0x([0-9a-f]+))?")
_BP_KEY = re.compile(r"(?i)basic\s*privacy", )
_ARC4 = re.compile(r"(?i)\bARC4\b|\bRC4\b")
_AES = re.compile(r"(?i)\bAES\b")


def probe_dmr_frames(frames: Iterable[dict]) -> EncryptionFinding:
    first_algid = None
    first_keyid = None
    evidence: List[str] = []
    for fr in frames:
        line = fr.get("log_line", "") or ""
        if m := _PI_LINE.search(line):
            try:
                alg = int(m.group(1), 16)
                if first_algid is None:
                    first_algid = alg
                if m.group(2) and first_keyid is None:
                    first_keyid = int(m.group(2), 16)
                evidence.append(line.strip())
                continue
            except ValueError:
                pass
        if (alg := fr.get("algid")) is not None and first_algid is None:
            first_algid = int(alg)
            evidence.append(f"voice-frame algid=0x{int(alg):02X}")
        if (key := fr.get("keyid")) is not None and first_keyid is None:
            first_keyid = int(key)
        if _BP_KEY.search(line) and first_algid is None:
            first_algid = 0x21   # synonym for DMR Basic Privacy
            evidence.append(line.strip())
        elif (_ARC4.search(line) or _AES.search(line)) and first_algid is None:
            first_algid = 0x25 if _ARC4.search(line) else 0x84
            evidence.append(line.strip())
    if first_algid is None:
        return EncryptionFinding(encrypted=False,
                                 evidence=["no DMR PI header observed"])
    name = DMR_ALG.get(first_algid, f"UNKNOWN(0x{first_algid:02X})")
    is_clear = first_algid in (0x00, 0x80)
    return EncryptionFinding(
        encrypted=not is_clear,
        algorithm=None if is_clear else name,
        algorithm_id=first_algid,
        key_id=first_keyid,
        evidence=evidence or [f"algid=0x{first_algid:02X}"],
    )
