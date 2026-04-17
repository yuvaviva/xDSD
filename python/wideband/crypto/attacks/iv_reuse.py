"""Cross-algorithm IV/MI reuse detector.

Finds repeated Message Indicator (MI) / IV values across frames within a
single channel. IV reuse under a stream cipher (RC4/DES-OFB/AES-OFB) means
XOR of two ciphertexts yields XOR of two plaintexts — trivially recoverable
when one plaintext is partially known.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, List, Optional

from ..report import AttackResult


def detect_iv_reuse(mis: Iterable[int]) -> AttackResult:
    mis = list(mis)
    if not mis:
        return AttackResult(module="iv_reuse", attempted=False, succeeded=False,
                            notes="no MIs observed")
    counts = Counter(mis)
    reused = {mi: c for mi, c in counts.items() if c >= 2}
    if not reused:
        return AttackResult(module="iv_reuse", attempted=True, succeeded=False,
                            notes=f"{len(counts)} distinct MIs observed, no reuse")
    most = max(reused.values())
    notes = (f"{len(reused)} MI value(s) repeated; "
             f"max repetition count {most}")
    return AttackResult(module="iv_reuse", attempted=True, succeeded=True,
                        confidence=min(1.0, most / 8.0), notes=notes)
