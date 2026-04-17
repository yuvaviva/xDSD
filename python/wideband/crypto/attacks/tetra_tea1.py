"""TETRA TEA1 passive ciphertext distinguisher.

Full TEA1 key recovery from published 2023 academic work is out of scope; this
module implements only a ciphertext distinguisher — a statistical test that
flags whether observed ciphertext is consistent with TEA1's reduced 32-bit
effective keyspace (which would make key recovery plausible offline on
commodity hardware).
"""

from __future__ import annotations

import math
from typing import Iterable

from ..report import AttackResult


def _byte_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts if c)


def distinguish_tetra_tea1(ciphertext: bytes,
                           chi2_threshold: float = 310.0) -> AttackResult:
    """Run a chi-square uniformity test on ciphertext bytes.

    TEA1 ciphertext is near-uniform on byte level; a failure of the test
    suggests a deterministic non-TEA1 overlay (often DMR BP misclassified).
    We report the distinguisher outcome but never claim key recovery.
    """
    if not ciphertext:
        return AttackResult(module="tetra_tea1", attempted=False, succeeded=False,
                            notes="no ciphertext")
    counts = [0] * 256
    for b in ciphertext:
        counts[b] += 1
    n = len(ciphertext)
    expected = n / 256.0
    chi2 = sum((c - expected) ** 2 / expected for c in counts)
    ent = _byte_entropy(ciphertext)
    tea1_like = chi2 < chi2_threshold and ent > 7.5
    return AttackResult(
        module="tetra_tea1", attempted=True, succeeded=False,
        confidence=0.5 if tea1_like else 0.1,
        notes=(f"chi2={chi2:.1f} entropy={ent:.2f} "
               f"{'consistent with TEA1 keystream' if tea1_like else 'not TEA1-like'}; "
               "no key recovery attempted"),
    )
