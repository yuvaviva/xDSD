"""Ingest-layer unit tests."""

from __future__ import annotations

import os
import tempfile

import numpy as np

from dsd.wideband.ingest import (
    HackRFInt8Reader,
    RtlSdrUint8Reader,
    GqrxFc32Reader,
    FormatProbe,
    ContiguousStream,
)


def _write_bytes(path: str, data: bytes) -> None:
    with open(path, "wb") as fh:
        fh.write(data)


def test_hackrf_int8_round_trip(tmp_path):
    n = 1024
    i = np.linspace(-120, 120, n, dtype=np.int8)
    q = np.linspace(120, -120, n, dtype=np.int8)
    interleaved = np.empty(n * 2, dtype=np.int8)
    interleaved[0::2] = i
    interleaved[1::2] = q
    p = tmp_path / "a.iq"
    interleaved.tofile(p)
    r = HackRFInt8Reader(str(p), sample_rate=1_000_000)
    blocks = list(r.read_blocks(512))
    joined = np.concatenate(blocks)
    assert joined.size == n
    assert np.allclose(joined.real[0], i[0] / 127.0, atol=1e-3)


def test_rtl_uint8(tmp_path):
    n = 256
    raw = np.full(n * 2, 127, dtype=np.uint8)
    p = tmp_path / "a.bin"
    raw.tofile(p)
    r = RtlSdrUint8Reader(str(p), sample_rate=1_000_000)
    blocks = list(r.read_blocks(256))
    assert np.concatenate(blocks).size == n


def test_format_probe_hint(tmp_path):
    p = tmp_path / "file.bin"
    _write_bytes(str(p), b"\x00" * 64)
    pr = FormatProbe.detect_file(str(p), hint="rtl_uint8")
    assert pr.reader_cls is RtlSdrUint8Reader


def test_contiguous_stream(tmp_path):
    for i in range(3):
        raw = np.full(200, 10, dtype=np.int8)
        il = np.empty(400, dtype=np.int8)
        il[0::2] = raw
        il[1::2] = raw
        il.tofile(tmp_path / f"hackrf_{i:03d}.iq")
    s = ContiguousStream(str(tmp_path), sample_rate=1_000_000,
                         format_hint="hackrf_int8", block_size=512)
    total = sum(b.size for b in s)
    assert total == 3 * 200
    assert s.gaps == []
