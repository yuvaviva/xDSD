"""TETRA encryption probe.

Feeds on ``TETRA_MAC_ENCR`` frames emitted by the ``tetra_rx`` adapter and
on ``ENCRYPTION_EVIDENCE`` rows carrying TEA1-4 mentions.
"""

from __future__ import annotations

import re
from typing import Iterable, List

from .schema import EncryptionFinding


_TEA_RE = re.compile(r"\bTEA([1-4])\b", re.IGNORECASE)


def probe_tetra_frames(frames: Iterable[dict]) -> EncryptionFinding:
    evidence: List[str] = []
    tea_variant: str | None = None
    security_class: int | None = None
    encrypted = False
    for fr in frames:
        t = fr.get("type")
        line = fr.get("log_line", "") or ""
        if t == "TETRA_MAC_ENCR":
            sc = fr.get("security_class")
            if sc is not None:
                security_class = int(sc)
                evidence.append(f"MAC-ENCR class {security_class}")
                if security_class > 0:
                    encrypted = True
        if m := _TEA_RE.search(line):
            tea_variant = f"TEA{m.group(1)}"
            evidence.append(tea_variant)
            encrypted = True
        if t == "ENCRYPTION_EVIDENCE" and line:
            evidence.append(line.strip())
            encrypted = True
    algorithm = tea_variant if tea_variant else ("TETRA-CIPHERED"
                                                 if encrypted else None)
    return EncryptionFinding(
        encrypted=encrypted,
        algorithm=algorithm,
        algorithm_id=security_class,
        evidence=evidence or (["no TETRA encryption evidence observed"]
                              if not encrypted else []),
    )
