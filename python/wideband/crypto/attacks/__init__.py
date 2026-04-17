"""Passive key-recovery attack registry (M6b).

All attacks consume captured ciphertext + metadata and return an
`AttackResult`. They are strictly passive — no transmission, no active probing.
Strong algorithms (AES, TEA2/3/4) always return attempted=False.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from ..report import AttackResult, EncryptionState

from .iv_reuse import detect_iv_reuse
from .p25_adp import attack_p25_adp
from .p25_des import attack_p25_des_known_key
from .dmr_bp import attack_dmr_basic_privacy
from .tetra_tea1 import distinguish_tetra_tea1


AttackFn = Callable[..., AttackResult]


def available_attacks() -> Dict[str, AttackFn]:
    return {
        "iv_reuse": detect_iv_reuse,
        "p25_adp": attack_p25_adp,
        "p25_des_known_key": attack_p25_des_known_key,
        "dmr_bp": attack_dmr_basic_privacy,
        "tetra_tea1": distinguish_tetra_tea1,
    }


__all__ = ["available_attacks", "AttackResult", "EncryptionState"]
