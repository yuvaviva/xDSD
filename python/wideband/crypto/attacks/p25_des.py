"""P25 DES-OFB: known-key decrypt only.

We do NOT brute-force single-DES inside this package — that is a specialised
workload. When the operator already has the key (from a legitimate source),
this module performs the decryption and returns the recovered plaintext.
"""

from __future__ import annotations

from typing import Optional

from ..report import AttackResult


def attack_p25_des_known_key(ciphertext: bytes, key_hex: Optional[str],
                             mi: Optional[int] = None, algid: int = 0x81
                             ) -> AttackResult:
    if algid != 0x81:
        return AttackResult(module="p25_des_known_key", attempted=False,
                            succeeded=False,
                            notes=f"algid 0x{algid:02X} is not DES-OFB")
    if not key_hex:
        return AttackResult(module="p25_des_known_key", attempted=False,
                            succeeded=False,
                            notes="no key provided in config; skipping")
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except Exception as exc:
        return AttackResult(module="p25_des_known_key", attempted=False,
                            succeeded=False,
                            notes=f"cryptography library unavailable: {exc}")
    key = bytes.fromhex(key_hex)
    if len(key) != 8:
        return AttackResult(module="p25_des_known_key", attempted=True,
                            succeeded=False,
                            notes=f"DES key must be 8 bytes, got {len(key)}")
    iv = (mi or 0).to_bytes(8, "big") if mi is not None else b"\x00" * 8
    try:
        c = Cipher(algorithms.TripleDES(key + key + key), modes.OFB(iv))
        dec = c.decryptor()
        pt = dec.update(ciphertext) + dec.finalize()
    except Exception as exc:
        return AttackResult(module="p25_des_known_key", attempted=True,
                            succeeded=False, notes=f"decrypt error: {exc}")
    return AttackResult(module="p25_des_known_key", attempted=True,
                        succeeded=True, key_hex=key_hex, confidence=1.0,
                        notes=f"{len(pt)} bytes decrypted with supplied key")
