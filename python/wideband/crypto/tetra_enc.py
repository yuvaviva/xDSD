"""TETRA encryption detection from tetra-rx log output."""

from __future__ import annotations

import re
from typing import Iterable, List

from .report import EncryptionState


_MAC_ENCR_RE = re.compile(r"MAC-ENCR.*?class\s*(\d+)", re.IGNORECASE)
_TEA_RE = re.compile(r"\bTEA[1-4]\b", re.IGNORECASE)
_CIPHERED_RE = re.compile(r"(?:ciphered|encrypted)\s*=\s*(1|true|yes)", re.IGNORECASE)


def probe_tetra_encryption(log_lines: Iterable[str]) -> EncryptionState:
    evidence: List[str] = []
    alg_name = None
    for line in log_lines:
        if m := _MAC_ENCR_RE.search(line):
            evidence.append(f"Security class {m.group(1)}")
        if m := _TEA_RE.search(line):
            alg_name = m.group(0).upper()
            evidence.append(alg_name)
        if _CIPHERED_RE.search(line):
            evidence.append(line.strip())
    encrypted = bool(evidence)
    # TEA1 is attackable academically; TEA2/3/4 are not.
    recoverable = alg_name == "TEA1"
    return EncryptionState(
        encrypted=encrypted,
        algorithm=alg_name,
        evidence=evidence,
        recoverable=recoverable,
    )
