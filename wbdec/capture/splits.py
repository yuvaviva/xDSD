"""Auto-split file discovery, ordering, and gap detection.

SDR capture tools roll over to a new file every N bytes (HackRF) or every
M seconds (SDR#, GQRX). We stitch them into a logical contiguous stream by:

1. Globbing the folder for the expected extension.
2. Sorting lexicographically — HackRF's ordinal filenames and SDR#'s
   ISO-style timestamps both sort correctly under lex order.
3. Recording gaps when a non-last file is smaller than the dominant size.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .readers import FORMATS, Reader, detect_format, open_reader


_EXT_GLOBS = {
    "hackrf_int8": ("*.iq", "*.bin", "*.raw", "*.dat"),
    "rtl_uint8":   ("*.bin", "*.raw", "*.dat"),
    "gqrx_fc32":   ("*.fc32", "*.cfile", "*.raw"),
    "sigmf":       ("*.sigmf-data",),
    "wav":         ("*.wav",),
}

_ANY_GLOBS = tuple(sorted({g for globs in _EXT_GLOBS.values() for g in globs}))


def list_split_files(folder: str, fmt: Optional[str] = None) -> List[str]:
    patterns = _EXT_GLOBS.get(fmt, _ANY_GLOBS) if fmt else _ANY_GLOBS
    found: set[str] = set()
    for pat in patterns:
        found.update(glob.glob(os.path.join(folder, pat)))
    return sorted(found)


@dataclass
class SplitGap:
    after_file: str
    expected_samples: int
    actual_samples: int
    dropped_samples: int


@dataclass
class SplitSet:
    """A sorted sequence of split files treated as one logical capture.

    Lazily opens readers; does not load any sample data until
    ``iter_chunks`` is invoked. ``sample_rate_hz`` and ``center_hz`` are taken
    from the first file (for SigMF) or from the arguments otherwise.
    """

    folder: str
    fmt: str
    sample_rate_hz: float
    center_hz: float
    files: List[str] = field(default_factory=list)
    expected_file_samples: Optional[int] = None
    gaps: List[SplitGap] = field(default_factory=list)

    @classmethod
    def discover(cls, folder: str, sample_rate_hz: float, center_hz: float = 0.0,
                 fmt: Optional[str] = None) -> "SplitSet":
        files = list_split_files(folder, fmt)
        if not files:
            raise FileNotFoundError(f"no capture files found in {folder}")
        resolved_fmt = fmt or detect_format(files[0])
        # For SigMF, pull sample_rate + center from the first file's metadata.
        if resolved_fmt == "sigmf":
            with open_reader(files[0], sample_rate_hz or 1.0, center_hz) as r:
                sample_rate_hz = r.sample_rate_hz
                center_hz = r.center_hz
        s = cls(
            folder=folder, fmt=resolved_fmt,
            sample_rate_hz=sample_rate_hz, center_hz=center_hz,
            files=files,
        )
        s._detect_expected_size()
        return s

    def _detect_expected_size(self) -> None:
        if len(self.files) < 2:
            return
        cls = FORMATS[self.fmt]
        sizes = [os.path.getsize(f) for f in self.files]
        # Use the most common size among all-but-last files.
        from collections import Counter
        c = Counter(sizes[:-1])
        expected_bytes, _ = c.most_common(1)[0]
        # WAV's "bytes_per_sample" is instance-dependent; HackRF/RTL/fc32
        # are class-constant, which is what we care about for gap detection.
        bps = getattr(cls, "bytes_per_sample", 2)
        self.expected_file_samples = expected_bytes // max(bps, 1)

    @property
    def total_samples(self) -> int:
        total = 0
        cls = FORMATS[self.fmt]
        bps = getattr(cls, "bytes_per_sample", 2)
        for p in self.files:
            total += os.path.getsize(p) // max(bps, 1)
        return total

    @property
    def duration_s(self) -> float:
        return self.total_samples / max(self.sample_rate_hz, 1.0)

    def iter_chunks(self, chunk_samples: int):
        """Yield (chunk_index, sample_offset_in_stream, complex64_array).

        Records a SplitGap whenever a non-last file is short relative to the
        expected file size.
        """
        cls = FORMATS[self.fmt]
        bps = getattr(cls, "bytes_per_sample", 2)
        stream_offset = 0
        last_idx = len(self.files) - 1
        chunk_index = 0
        for i, path in enumerate(self.files):
            with open_reader(path, self.sample_rate_hz, self.center_hz, fmt=self.fmt) as r:
                n_in_file = r.sample_count
                if (self.expected_file_samples is not None
                        and i != last_idx
                        and n_in_file < self.expected_file_samples):
                    self.gaps.append(SplitGap(
                        after_file=path,
                        expected_samples=self.expected_file_samples,
                        actual_samples=n_in_file,
                        dropped_samples=self.expected_file_samples - n_in_file,
                    ))
                off = 0
                while off < n_in_file:
                    n = min(chunk_samples, n_in_file - off)
                    chunk = r.read_chunk(off, n)
                    yield chunk_index, stream_offset, chunk
                    chunk_index += 1
                    off += n
                    stream_offset += n
