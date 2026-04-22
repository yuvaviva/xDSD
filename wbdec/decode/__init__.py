"""Decode stage: pluggable protocol adapters + process-pool orchestration."""

from .base import (
    DecodeResult,
    DecodeOptions,
    FrameRecord,
    ProtocolAdapter,
)
from .registry import register_adapter, get_adapters_for, all_adapters
from .dsd_fme import DsdFmeAdapter
from .gr_dsd import GrDsdAdapter
from .tetra_rx import TetraRxAdapter
from .tetra_native import TetraNativeAdapter
from .run import run_decode

__all__ = [
    "DecodeResult", "DecodeOptions", "FrameRecord", "ProtocolAdapter",
    "register_adapter", "get_adapters_for", "all_adapters",
    "DsdFmeAdapter", "GrDsdAdapter", "TetraRxAdapter", "TetraNativeAdapter",
    "run_decode",
]
