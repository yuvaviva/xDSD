"""Per-format readers producing complex64 samples from a single file."""

from __future__ import annotations

import glob
import json
import os
import re
import struct
from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple

import numpy as np


class Reader:
    """Base reader. Subclasses stream complex64 samples from one file."""

    def __init__(self, path: str, sample_rate: float, center_hz: float = 0.0):
        self.path = path
        self.sample_rate = sample_rate
        self.center_hz = center_hz

    @property
    def bytes_per_sample(self) -> int:
        raise NotImplementedError

    def sample_count(self) -> int:
        return os.path.getsize(self.path) // self.bytes_per_sample

    def read_blocks(self, block_size: int) -> Iterator[np.ndarray]:
        raise NotImplementedError


class HackRFInt8Reader(Reader):
    """hackrf_transfer raw output: interleaved int8 I,Q."""

    @property
    def bytes_per_sample(self) -> int:
        return 2  # I8 + Q8

    def read_blocks(self, block_size: int) -> Iterator[np.ndarray]:
        with open(self.path, "rb") as fh:
            while True:
                buf = fh.read(block_size * 2)
                if not buf:
                    return
                raw = np.frombuffer(buf, dtype=np.int8)
                if raw.size % 2:
                    raw = raw[:-1]
                iq = raw.astype(np.float32).view()
                i = iq[0::2] / 127.0
                q = iq[1::2] / 127.0
                yield (i + 1j * q).astype(np.complex64)


class RtlSdrUint8Reader(Reader):
    """rtl_sdr raw output: interleaved uint8 I,Q centered at 127.5."""

    @property
    def bytes_per_sample(self) -> int:
        return 2

    def read_blocks(self, block_size: int) -> Iterator[np.ndarray]:
        with open(self.path, "rb") as fh:
            while True:
                buf = fh.read(block_size * 2)
                if not buf:
                    return
                raw = np.frombuffer(buf, dtype=np.uint8).astype(np.float32)
                if raw.size % 2:
                    raw = raw[:-1]
                i = (raw[0::2] - 127.5) / 127.5
                q = (raw[1::2] - 127.5) / 127.5
                yield (i + 1j * q).astype(np.complex64)


class GqrxFc32Reader(Reader):
    """GQRX / SDR# complex float32 baseband dump."""

    @property
    def bytes_per_sample(self) -> int:
        return 8  # two float32

    def read_blocks(self, block_size: int) -> Iterator[np.ndarray]:
        with open(self.path, "rb") as fh:
            while True:
                buf = fh.read(block_size * 8)
                if not buf:
                    return
                arr = np.frombuffer(buf, dtype=np.float32)
                if arr.size % 2:
                    arr = arr[:-1]
                yield (arr[0::2] + 1j * arr[1::2]).astype(np.complex64)


class SigMFReader(Reader):
    """Reads a SigMF data file using metadata from the paired .sigmf-meta."""

    def __init__(self, path: str, sample_rate: float, center_hz: float = 0.0,
                 meta_path: Optional[str] = None):
        super().__init__(path, sample_rate, center_hz)
        if meta_path is None:
            meta_path = os.path.splitext(path)[0] + ".sigmf-meta"
            if not os.path.exists(meta_path):
                alt = path.replace(".sigmf-data", ".sigmf-meta")
                meta_path = alt if os.path.exists(alt) else meta_path
        with open(meta_path, "r") as fh:
            self.meta = json.load(fh)
        g = self.meta.get("global", {})
        self.datatype = g.get("core:datatype", "cf32_le")
        self.sample_rate = float(g.get("core:sample_rate", sample_rate))
        captures = self.meta.get("captures", [{}])
        self.center_hz = float(captures[0].get("core:frequency", center_hz))

    @property
    def bytes_per_sample(self) -> int:
        dt = self.datatype
        if dt.startswith("cf32"):
            return 8
        if dt.startswith("ci16") or dt.startswith("cs16"):
            return 4
        if dt.startswith("ci8") or dt.startswith("cs8"):
            return 2
        if dt.startswith("cu8"):
            return 2
        raise ValueError(f"Unsupported SigMF datatype: {dt}")

    def read_blocks(self, block_size: int) -> Iterator[np.ndarray]:
        dt = self.datatype
        with open(self.path, "rb") as fh:
            while True:
                buf = fh.read(block_size * self.bytes_per_sample)
                if not buf:
                    return
                if dt.startswith("cf32"):
                    arr = np.frombuffer(buf, dtype="<f4")
                    yield (arr[0::2] + 1j * arr[1::2]).astype(np.complex64)
                elif dt.startswith("ci16") or dt.startswith("cs16"):
                    arr = np.frombuffer(buf, dtype="<i2").astype(np.float32) / 32768.0
                    yield (arr[0::2] + 1j * arr[1::2]).astype(np.complex64)
                elif dt.startswith("cs8") or dt.startswith("ci8"):
                    arr = np.frombuffer(buf, dtype=np.int8).astype(np.float32) / 127.0
                    yield (arr[0::2] + 1j * arr[1::2]).astype(np.complex64)
                elif dt.startswith("cu8"):
                    arr = (np.frombuffer(buf, dtype=np.uint8).astype(np.float32)
                           - 127.5) / 127.5
                    yield (arr[0::2] + 1j * arr[1::2]).astype(np.complex64)
                else:
                    raise ValueError(f"Unsupported SigMF datatype: {dt}")


class WavReader(Reader):
    """WAV file reader. Assumes stereo = complex IQ; mono = real FM-demod."""

    def __init__(self, path: str, sample_rate: float, center_hz: float = 0.0):
        import wave
        self._wav = wave.open(path, "rb")
        self.n_channels = self._wav.getnchannels()
        self.sampwidth = self._wav.getsampwidth()
        sr = float(self._wav.getframerate())
        super().__init__(path, sr, center_hz)

    @property
    def bytes_per_sample(self) -> int:
        return self.n_channels * self.sampwidth

    def read_blocks(self, block_size: int) -> Iterator[np.ndarray]:
        w = self._wav
        sw = self.sampwidth
        nc = self.n_channels
        while True:
            raw = w.readframes(block_size)
            if not raw:
                w.close()
                return
            if sw == 2:
                arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            elif sw == 1:
                arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
                       - 128.0) / 128.0
            else:
                raise ValueError(f"Unsupported wav sample width: {sw}")
            if nc == 2:
                yield (arr[0::2] + 1j * arr[1::2]).astype(np.complex64)
            else:
                yield arr.astype(np.complex64)


# ---------------------------------------------------------------------------
# Format probe
# ---------------------------------------------------------------------------

_HACKRF_RE = re.compile(r".*\.(iq|bin)$", re.I)
_RTL_RE = re.compile(r".*\.(raw|bin)$", re.I)
_FC32_RE = re.compile(r".*\.(fc32|cfile|raw)$", re.I)
_SIGMF_DATA_RE = re.compile(r".*\.sigmf-data$", re.I)


@dataclass
class ProbeResult:
    fmt: str
    reader_cls: type
    sample_rate: Optional[float]
    center_hz: Optional[float]


class FormatProbe:
    """Sniff a file (or a folder's dominant format) to pick a Reader class."""

    @staticmethod
    def detect_file(path: str, hint: Optional[str] = None) -> ProbeResult:
        low = path.lower()
        if hint:
            return FormatProbe._from_hint(hint)
        if low.endswith(".sigmf-data"):
            return ProbeResult("sigmf", SigMFReader, None, None)
        if low.endswith(".wav"):
            return ProbeResult("wav", WavReader, None, None)
        if low.endswith(".fc32") or low.endswith(".cfile"):
            return ProbeResult("gqrx_fc32", GqrxFc32Reader, None, None)
        # Ambiguous .iq/.bin/.raw: rely on a hint or byte-level heuristic.
        # HackRF files are typically large and int8; RTL is uint8. Without a
        # ground-truth header we default to HackRF int8 which is the most
        # common wideband capture format.
        return ProbeResult("hackrf_int8", HackRFInt8Reader, None, None)

    @staticmethod
    def _from_hint(hint: str) -> ProbeResult:
        h = hint.lower()
        mapping = {
            "hackrf_int8": ("hackrf_int8", HackRFInt8Reader),
            "hackrf": ("hackrf_int8", HackRFInt8Reader),
            "rtl_uint8": ("rtl_uint8", RtlSdrUint8Reader),
            "rtl": ("rtl_uint8", RtlSdrUint8Reader),
            "gqrx_fc32": ("gqrx_fc32", GqrxFc32Reader),
            "fc32": ("gqrx_fc32", GqrxFc32Reader),
            "sigmf": ("sigmf", SigMFReader),
            "wav": ("wav", WavReader),
        }
        if h not in mapping:
            raise ValueError(f"Unknown format hint: {hint}")
        fmt, cls = mapping[h]
        return ProbeResult(fmt, cls, None, None)

    @staticmethod
    def list_folder(folder: str, hint: Optional[str] = None) -> List[str]:
        """Return a sorted list of data files in folder filtered by format hint."""
        patterns: Tuple[str, ...]
        if hint:
            hl = hint.lower()
            if hl.startswith("sigmf"):
                patterns = ("*.sigmf-data",)
            elif hl in ("gqrx_fc32", "fc32"):
                patterns = ("*.fc32", "*.cfile")
            elif hl == "wav":
                patterns = ("*.wav",)
            else:
                patterns = ("*.iq", "*.bin", "*.raw", "*.dat")
        else:
            patterns = ("*.iq", "*.bin", "*.raw", "*.dat", "*.sigmf-data",
                        "*.fc32", "*.cfile", "*.wav")
        found: List[str] = []
        for pat in patterns:
            found.extend(glob.glob(os.path.join(folder, pat)))
        # Sort by filename; HackRF ordinal and SDR# timestamp names both sort
        # correctly lexicographically. ContiguousStream also verifies ordering.
        return sorted(set(found))
