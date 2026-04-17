"""P25 encryption detection from dsd_state.algid/keyid.

P25 algorithm IDs (ANSI/TIA-102.AABF):
    0x80  No encryption (clear)
    0x81  DES-OFB
    0x83  ``Triple DES''
    0x84  AES-256
    0x85  RC4 ("ADP")
    0xAA  RC4 (alternate)
"""

from __future__ import annotations

from typing import Optional

from .report import EncryptionState


_P25_ALG_NAMES = {
    0x80: "CLEAR",
    0x81: "DES-OFB",
    0x83: "3DES",
    0x84: "AES-256",
    0x85: "ADP-RC4",
    0xAA: "ARC4",
}


def probe_p25_encryption(algid: Optional[int], keyid: Optional[int]
                         ) -> EncryptionState:
    if algid is None:
        return EncryptionState(encrypted=False, evidence=["no HDU observed"])
    alg_name = _P25_ALG_NAMES.get(int(algid), f"UNKNOWN(0x{int(algid):02X})")
    is_clear = int(algid) == 0x80
    # ADP and single-DES are considered potentially recoverable under M6b.
    recoverable = int(algid) in (0x81, 0x85, 0xAA)
    return EncryptionState(
        encrypted=not is_clear,
        algorithm=alg_name if not is_clear else None,
        algorithm_id=int(algid),
        key_id=int(keyid) if keyid is not None else None,
        evidence=[f"HDU algid=0x{int(algid):02X}"],
        recoverable=recoverable and not is_clear,
    )
