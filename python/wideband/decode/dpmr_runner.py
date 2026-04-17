"""dPMR: detection-only stub.

dPMR 446 and dPMR tier 1/2/3 are 6.25 kHz FDMA 4FSK. Upstream DSD has no
decoder for dPMR, and a full port is out of scope for M5. This module exists
so the pipeline has a consistent interface for every label; it returns a
structured "unsupported" result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class DpmrDecodeResult:
    ok: bool
    pcm_8k: Optional[np.ndarray]
    note: str


def decode_dpmr_stub(discriminator_48k: np.ndarray) -> DpmrDecodeResult:
    return DpmrDecodeResult(
        ok=False,
        pcm_8k=None,
        note=("dPMR decode not implemented. Signal detected and "
              "classified; raw baseband is preserved for later offline decode."),
    )
