"""DMR PI (Privacy Indicator) header parser.

The PI header is a LC opcode 0x22 carrying:
    - ALG ID    (8 bits)      0x21 = Basic Privacy (proprietary), 0x25 = ARC4, 0x84 = AES
    - KEY ID    (8 bits)
    - MI        (32 bits) — message indicator / IV
    - CRC etc.

This parser is intentionally minimal — upstream dsd does not surface PI
headers to Python, so we operate on a raw bit-stream snapshot if the runner
exposes one. If not, returns an "unknown" state.
"""

from __future__ import annotations

from typing import Optional

from .report import EncryptionState


_DMR_ALG_NAMES = {
    0x00: "CLEAR",
    0x21: "BASIC-PRIVACY",
    0x25: "ARC4",
    0x84: "AES",
}


def probe_dmr_pi_header(pi_header_bytes: Optional[bytes]) -> EncryptionState:
    if not pi_header_bytes or len(pi_header_bytes) < 6:
        return EncryptionState(encrypted=False, evidence=["no PI header seen"])
    alg = pi_header_bytes[0]
    key_id = pi_header_bytes[1]
    name = _DMR_ALG_NAMES.get(alg, f"UNKNOWN(0x{alg:02X})")
    is_clear = alg == 0x00
    recoverable = alg in (0x21, 0x25)  # BP scrambler + ARC4 are attackable
    return EncryptionState(
        encrypted=not is_clear,
        algorithm=name if not is_clear else None,
        algorithm_id=alg,
        key_id=key_id,
        evidence=[f"PI header alg=0x{alg:02X} keyid=0x{key_id:02X}"],
        recoverable=recoverable and not is_clear,
    )
