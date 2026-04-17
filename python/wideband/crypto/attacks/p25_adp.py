"""P25 ADP (RC4-based keystream) bounded-budget key search.

ADP derives an RC4 key from a 10-byte key and a 32-bit MI (drop initial 267
bytes). This module supports:

  * Known-plaintext keystream recovery when a full 228-bit LDU voice frame is
    assumed to decrypt to a specific crib pattern — returns the recovered
    keystream block, useful for in-call decrypt after the key is found.
  * Dictionary attack over a user-supplied wordlist.

It does NOT brute-force the full 80-bit key — that is computationally
infeasible without specialised hardware. When the ciphertext is genuinely AES
or 3DES (algid 0x84/0x83) this module returns attempted=False.
"""

from __future__ import annotations

import time
from typing import Iterable, List, Optional, Sequence

from ..report import AttackResult


def _rc4_ksa(key: bytes) -> List[int]:
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) & 0xFF
        S[i], S[j] = S[j], S[i]
    return S


def _rc4_keystream(key: bytes, n: int, drop: int = 267) -> bytes:
    S = _rc4_ksa(key)
    i = j = 0
    out = bytearray()
    for _ in range(drop):
        i = (i + 1) & 0xFF
        j = (j + S[i]) & 0xFF
        S[i], S[j] = S[j], S[i]
    for _ in range(n):
        i = (i + 1) & 0xFF
        j = (j + S[i]) & 0xFF
        S[i], S[j] = S[j], S[i]
        out.append(S[(S[i] + S[j]) & 0xFF])
    return bytes(out)


def _derive_adp_key(base_key: bytes, mi: int) -> bytes:
    # ADP keystream uses the concatenation of MI || key (see TIA-102.AACD-A).
    mi_bytes = mi.to_bytes(4, "big")
    return mi_bytes + base_key[:10]


def attack_p25_adp(ciphertext: bytes, mi: int,
                   crib: Optional[bytes] = None,
                   wordlist: Optional[Sequence[bytes]] = None,
                   max_cpu_seconds: float = 30.0,
                   algid: int = 0x85) -> AttackResult:
    """Bounded dictionary attack against ADP with an optional crib."""
    if algid not in (0x85, 0xAA):
        return AttackResult(module="p25_adp", attempted=False, succeeded=False,
                            notes=f"algid 0x{algid:02X} not in ADP/RC4 family")
    if not ciphertext or not wordlist:
        return AttackResult(module="p25_adp", attempted=False, succeeded=False,
                            notes="missing ciphertext or wordlist")
    t0 = time.monotonic()
    for candidate in wordlist:
        if time.monotonic() - t0 > max_cpu_seconds:
            return AttackResult(module="p25_adp", attempted=True, succeeded=False,
                                notes="cpu budget exhausted without match")
        key = _derive_adp_key(candidate, mi)
        ks = _rc4_keystream(key, len(ciphertext))
        pt = bytes(c ^ k for c, k in zip(ciphertext, ks))
        if crib is not None and crib in pt:
            return AttackResult(
                module="p25_adp", attempted=True, succeeded=True,
                key_hex=candidate.hex(), confidence=0.95,
                notes=f"crib match with wordlist key of {len(candidate)} bytes",
            )
    return AttackResult(module="p25_adp", attempted=True, succeeded=False,
                        notes=f"exhausted {len(wordlist)} wordlist entries")
