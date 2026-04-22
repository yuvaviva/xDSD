"""Uniform encryption-finding schema + algorithm-id name maps."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# P25 algorithm IDs (TIA-102.AABF).
P25_ALG = {
    0x80: "CLEAR",
    0x81: "DES-OFB",
    0x83: "3DES",
    0x84: "AES-256",
    0x85: "ADP-RC4",
    0xAA: "ARC4",
}

# DMR PI-header algorithm IDs.
DMR_ALG = {
    0x00: "CLEAR",
    0x21: "BASIC-PRIVACY",
    0x25: "ARC4",
    0x84: "AES",
}

ALGID_MAPS = {"p25": P25_ALG, "dmr": DMR_ALG}


@dataclass
class EncryptionFinding:
    """Per-channel aggregated encryption state."""
    encrypted: bool = False
    algorithm: Optional[str] = None
    algorithm_id: Optional[int] = None
    key_id: Optional[int] = None
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
