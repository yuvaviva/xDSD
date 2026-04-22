"""Capture layer: mmap-aware split stitching + per-format readers."""

from .readers import (
    Reader,
    HackRFInt8Reader,
    RtlSdrUint8Reader,
    GqrxFc32Reader,
    SigMFReader,
    WavReader,
    detect_format,
    open_reader,
    FORMATS,
)
from .splits import SplitSet, list_split_files
from .sigmf_view import VirtualSigMF, write_view_meta

__all__ = [
    "Reader",
    "HackRFInt8Reader",
    "RtlSdrUint8Reader",
    "GqrxFc32Reader",
    "SigMFReader",
    "WavReader",
    "detect_format",
    "open_reader",
    "FORMATS",
    "SplitSet",
    "list_split_files",
    "VirtualSigMF",
    "write_view_meta",
]
