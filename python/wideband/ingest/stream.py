"""ContiguousStream: stitch a sorted list of split recordings into one stream."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterator, List, Optional

import numpy as np

from .readers import Reader, FormatProbe, SigMFReader


@dataclass
class StreamGap:
    after_file: str
    expected_bytes: int
    actual_bytes: int
    dropped_samples: int


class ContiguousStream:
    """Iterate complex64 blocks across a folder of auto-split recordings.

    Assumes all files use the same format. Sorts files lexicographically
    (HackRF ordinal + SDR# timestamp + rtl_sdr suffix all sort correctly).
    Files are compared against an expected-size tolerance; a short trailing
    file (end-of-run) is accepted, but a short middle file is flagged as a
    gap and recorded for the final report.
    """

    def __init__(self, folder: str, sample_rate: float, center_hz: float = 0.0,
                 format_hint: Optional[str] = None, block_size: int = 1 << 20,
                 expected_file_bytes: Optional[int] = None):
        self.folder = folder
        self.sample_rate = sample_rate
        self.center_hz = center_hz
        self.format_hint = format_hint
        self.block_size = block_size
        self.expected_file_bytes = expected_file_bytes
        self.gaps: List[StreamGap] = []
        self.files = FormatProbe.list_folder(folder, format_hint)
        if not self.files:
            raise FileNotFoundError(f"No recordings found in {folder}")

    def _open(self, path: str) -> Reader:
        probe = FormatProbe.detect_file(path, self.format_hint)
        cls = probe.reader_cls
        if cls is SigMFReader:
            r = SigMFReader(path, self.sample_rate, self.center_hz)
            # SigMF overrides sample_rate/center_hz from metadata.
            self.sample_rate = r.sample_rate
            self.center_hz = r.center_hz
            return r
        return cls(path, self.sample_rate, self.center_hz)

    def total_samples_estimate(self) -> int:
        total = 0
        for p in self.files:
            probe = FormatProbe.detect_file(p, self.format_hint)
            bps = probe.reader_cls(p, self.sample_rate).bytes_per_sample  # type: ignore
            total += os.path.getsize(p) // bps
        return total

    def __iter__(self) -> Iterator[np.ndarray]:
        for i, path in enumerate(self.files):
            reader = self._open(path)
            file_bytes = os.path.getsize(path)
            if (self.expected_file_bytes is not None
                    and i < len(self.files) - 1
                    and file_bytes < self.expected_file_bytes):
                dropped = ((self.expected_file_bytes - file_bytes)
                           // reader.bytes_per_sample)
                self.gaps.append(StreamGap(
                    after_file=path,
                    expected_bytes=self.expected_file_bytes,
                    actual_bytes=file_bytes,
                    dropped_samples=dropped,
                ))
            yield from reader.read_blocks(self.block_size)
