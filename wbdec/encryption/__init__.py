"""Encryption detection — pure metadata pass over decoder frame streams.

No cryptanalysis. For each protocol family, map the adapter-parsed fields
(algid / keyid / MAC-ENCR evidence) onto a uniform ``EncryptionFinding``.
"""

from .schema import EncryptionFinding, ALGID_MAPS
from .p25 import probe_p25_frames
from .dmr import probe_dmr_frames
from .tetra import probe_tetra_frames
from .aggregator import probe_frames

__all__ = [
    "EncryptionFinding",
    "ALGID_MAPS",
    "probe_p25_frames",
    "probe_dmr_frames",
    "probe_tetra_frames",
    "probe_frames",
]
