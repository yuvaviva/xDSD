"""Per-event decoder runners. One module per protocol family."""

from .dsd_runner import decode_with_dsd, DsdDecodeResult
from .dsdplus_runner import decode_with_dsd_subprocess, DsdSubprocessResult
from .tetra_runner import decode_with_tetra_rx, TetraDecodeResult
from .dpmr_runner import decode_dpmr_stub, DpmrDecodeResult

__all__ = [
    "decode_with_dsd",
    "DsdDecodeResult",
    "decode_with_dsd_subprocess",
    "DsdSubprocessResult",
    "decode_with_tetra_rx",
    "TetraDecodeResult",
    "decode_dpmr_stub",
    "DpmrDecodeResult",
]
