"""Per-format readers, all memory-mapped where the kernel permits.

Each reader presents a uniform interface:

    - ``bytes_per_sample``: number of bytes per complex sample on disk
    - ``sample_count``: total samples in the file
    - ``read_chunk(start, n)``: read ``n`` complex64 samples starting at sample
      offset ``start``. Implementations use mmap so only the touched pages
      are paged in; reading a 50 GB file costs you the chunk, not the file.
    - ``read_blocks(chunk_samples)``: generator of sequential chunks

Formats supported: HackRF int8, rtl_sdr uint8, GQRX/SDR# cf32, SigMF, WAV.
"""

from __future__ import annotations

import json
import mmap
import os
import struct
import wave
from dataclasses import dataclass
from typing import Iterator, Optional, Type

import numpy as np


class Reader:
    """Base class. Subclasses must set ``bytes_per_sample`` and implement
    ``_read_raw_bytes(start_sample, n_samples) -> np.ndarray[int8/uint8/etc.]``
    (the raw dtype, not complex64). ``read_chunk`` converts to complex64.
    """

    name = "base"
    bytes_per_sample: int = 0              # overridden in subclass
    _raw_dtype: np.dtype = np.dtype("u1")  # overridden in subclass

    def __init__(self, path: str, sample_rate_hz: float, center_hz: float = 0.0):
        self.path = path
        self.sample_rate_hz = float(sample_rate_hz)
        self.center_hz = float(center_hz)
        self._mm: Optional[mmap.mmap] = None
        self._fh = None
        self._size = os.path.getsize(path)

    # -- resource management ------------------------------------------------

    def _ensure_mm(self) -> mmap.mmap:
        if self._mm is None:
            self._fh = open(self.path, "rb")
            self._mm = mmap.mmap(self._fh.fileno(), 0, access=mmap.ACCESS_READ)
        return self._mm

    def close(self) -> None:
        if self._mm is not None:
            self._mm.close()
            self._mm = None
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def __enter__(self):
        self._ensure_mm()
        return self

    def __exit__(self, *exc):
        self.close()

    # -- layout -------------------------------------------------------------

    @property
    def sample_count(self) -> int:
        return self._size // self.bytes_per_sample

    # -- reads --------------------------------------------------------------

    def read_chunk(self, start_sample: int, n_samples: int) -> np.ndarray:
        """Return ``n_samples`` complex64 samples starting at ``start_sample``."""
        raise NotImplementedError

    def read_blocks(self, chunk_samples: int) -> Iterator[np.ndarray]:
        off = 0
        total = self.sample_count
        while off < total:
            n = min(chunk_samples, total - off)
            yield self.read_chunk(off, n)
            off += n


# ---------------------------------------------------------------------------
# Interleaved-integer formats (HackRF int8, rtl_sdr uint8)
# ---------------------------------------------------------------------------

class HackRFInt8Reader(Reader):
    name = "hackrf_int8"
    bytes_per_sample = 2       # I8 + Q8

    def read_chunk(self, start_sample: int, n_samples: int) -> np.ndarray:
        mm = self._ensure_mm()
        off = start_sample * 2
        raw = np.frombuffer(mm, dtype=np.int8, count=n_samples * 2, offset=off)
        i = raw[0::2].astype(np.float32) / 127.0
        q = raw[1::2].astype(np.float32) / 127.0
        return (i + 1j * q).astype(np.complex64)


class RtlSdrUint8Reader(Reader):
    name = "rtl_uint8"
    bytes_per_sample = 2       # I8 + Q8, biased at 127.5

    def read_chunk(self, start_sample: int, n_samples: int) -> np.ndarray:
        mm = self._ensure_mm()
        off = start_sample * 2
        raw = np.frombuffer(mm, dtype=np.uint8, count=n_samples * 2, offset=off)
        arr = raw.astype(np.float32)
        i = (arr[0::2] - 127.5) / 127.5
        q = (arr[1::2] - 127.5) / 127.5
        return (i + 1j * q).astype(np.complex64)


class GqrxFc32Reader(Reader):
    """GQRX / SDR# / cfile — interleaved complex float32."""
    name = "gqrx_fc32"
    bytes_per_sample = 8

    def read_chunk(self, start_sample: int, n_samples: int) -> np.ndarray:
        mm = self._ensure_mm()
        off = start_sample * 8
        raw = np.frombuffer(mm, dtype="<f4", count=n_samples * 2, offset=off)
        return (raw[0::2] + 1j * raw[1::2]).astype(np.complex64)


# ---------------------------------------------------------------------------
# SigMF
# ---------------------------------------------------------------------------

class SigMFReader(Reader):
    """Reader for SigMF data files. The paired ``.sigmf-meta`` is consulted
    for datatype, sample_rate, and capture center frequency.
    """
    name = "sigmf"
    bytes_per_sample = 8  # overridden at init from metadata

    def __init__(self, path: str, sample_rate_hz: float = 0.0, center_hz: float = 0.0,
                 meta_path: Optional[str] = None):
        super().__init__(path, sample_rate_hz or 1.0, center_hz)
        if meta_path is None:
            if path.endswith(".sigmf-data"):
                meta_path = path[:-len(".sigmf-data")] + ".sigmf-meta"
            else:
                meta_path = os.path.splitext(path)[0] + ".sigmf-meta"
        with open(meta_path, "r") as fh:
            self.meta = json.load(fh)
        g = self.meta.get("global", {})
        self.datatype = g.get("core:datatype", "cf32_le")
        self.sample_rate_hz = float(g.get("core:sample_rate", sample_rate_hz))
        captures = self.meta.get("captures", [{}])
        self.center_hz = float(captures[0].get("core:frequency", center_hz))
        self.bytes_per_sample = _sigmf_bytes_per_sample(self.datatype)

    def read_chunk(self, start_sample: int, n_samples: int) -> np.ndarray:
        mm = self._ensure_mm()
        off = start_sample * self.bytes_per_sample
        dt = self.datatype
        if dt.startswith("cf32"):
            raw = np.frombuffer(mm, dtype="<f4", count=n_samples * 2, offset=off)
            return (raw[0::2] + 1j * raw[1::2]).astype(np.complex64)
        if dt.startswith("ci16") or dt.startswith("cs16"):
            raw = np.frombuffer(mm, dtype="<i2", count=n_samples * 2, offset=off)
            return ((raw[0::2] + 1j * raw[1::2]).astype(np.complex64)
                    / np.float32(32768.0))
        if dt.startswith("ci8") or dt.startswith("cs8"):
            raw = np.frombuffer(mm, dtype=np.int8, count=n_samples * 2, offset=off)
            return ((raw[0::2] + 1j * raw[1::2]).astype(np.complex64)
                    / np.float32(127.0))
        if dt.startswith("cu8"):
            raw = np.frombuffer(mm, dtype=np.uint8, count=n_samples * 2, offset=off)
            arr = raw.astype(np.float32)
            return ((arr[0::2] - 127.5) + 1j * (arr[1::2] - 127.5)) / np.float32(127.5)
        raise ValueError(f"Unsupported SigMF datatype: {dt}")


def _sigmf_bytes_per_sample(dt: str) -> int:
    if dt.startswith("cf32"):
        return 8
    if dt.startswith("ci16") or dt.startswith("cs16"):
        return 4
    if dt.startswith("ci8") or dt.startswith("cs8") or dt.startswith("cu8"):
        return 2
    raise ValueError(f"Unsupported SigMF datatype: {dt}")


# ---------------------------------------------------------------------------
# WAV
# ---------------------------------------------------------------------------

class WavReader(Reader):
    """WAV reader. Stereo = complex IQ; mono = real (FM discriminator)."""
    name = "wav"

    def __init__(self, path: str, sample_rate_hz: float = 0.0, center_hz: float = 0.0):
        self._wav = wave.open(path, "rb")
        self.n_channels = self._wav.getnchannels()
        self.sampwidth = self._wav.getsampwidth()
        sr = float(self._wav.getframerate())
        super().__init__(path, sample_rate_hz=sr, center_hz=center_hz)
        self.bytes_per_sample = self.n_channels * self.sampwidth
        # Load everything into memory — WAV files are typically small.
        self._buf = self._read_all()
        self._wav.close()

    def _read_all(self) -> np.ndarray:
        n = self._wav.getnframes()
        raw = self._wav.readframes(n)
        if self.sampwidth == 2:
            arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        elif self.sampwidth == 1:
            arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
                   - 128.0) / 128.0
        else:
            raise ValueError(f"Unsupported wav sample width: {self.sampwidth}")
        if self.n_channels == 2:
            return (arr[0::2] + 1j * arr[1::2]).astype(np.complex64)
        return arr.astype(np.complex64)

    @property
    def sample_count(self) -> int:
        return len(self._buf)

    def read_chunk(self, start_sample: int, n_samples: int) -> np.ndarray:
        return self._buf[start_sample: start_sample + n_samples]


# ---------------------------------------------------------------------------
# Format detection + factory
# ---------------------------------------------------------------------------

FORMATS: dict[str, Type[Reader]] = {
    "hackrf_int8": HackRFInt8Reader,
    "rtl_uint8":  RtlSdrUint8Reader,
    "gqrx_fc32":  GqrxFc32Reader,
    "sigmf":      SigMFReader,
    "wav":        WavReader,
}


def detect_format(path: str) -> str:
    low = path.lower()
    if low.endswith(".sigmf-data"):
        return "sigmf"
    if low.endswith(".wav"):
        return "wav"
    if low.endswith(".fc32") or low.endswith(".cfile"):
        return "gqrx_fc32"
    # Ambiguous .iq/.bin/.raw: caller should pass a hint. Default to HackRF
    # int8 which is the most common wideband capture format.
    return "hackrf_int8"


def open_reader(path: str, sample_rate_hz: float, center_hz: float = 0.0,
                fmt: Optional[str] = None) -> Reader:
    name = fmt or detect_format(path)
    cls = FORMATS.get(name)
    if cls is None:
        raise ValueError(f"Unknown format: {name}")
    return cls(path, sample_rate_hz=sample_rate_hz, center_hz=center_hz)
