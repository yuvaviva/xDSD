"""Aggregated encryption reporting per decoded channel."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class EncryptionState:
    encrypted: bool
    algorithm: Optional[str] = None
    algorithm_id: Optional[int] = None
    key_id: Optional[int] = None
    evidence: List[str] = field(default_factory=list)
    recoverable: bool = False


@dataclass
class AttackResult:
    module: str
    attempted: bool
    succeeded: bool
    key_hex: Optional[str] = None
    confidence: float = 0.0
    notes: str = ""


@dataclass
class EncryptionReport:
    state: EncryptionState
    attacks: List[AttackResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": asdict(self.state),
            "attacks": [asdict(a) for a in self.attacks],
        }
