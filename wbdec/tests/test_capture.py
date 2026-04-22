"""Capture-layer tests: readers + splits + SigMF view."""

from __future__ import annotations

import json
import os

import numpy as np

from wbdec.capture import (
    HackRFInt8Reader, RtlSdrUint8Reader, GqrxFc32Reader,
    SplitSet, VirtualSigMF, write_view_meta, open_reader, detect_format,
)
from wbdec.tests._synth import write_hackrf_int8, synth_4fsk


def test_hackrf_reader_mmap(tmp_path):
    n = 1024
    iq = synth_4fsk(n, 100_000, 4800, 1800)
    p = write_hackrf_int8(str(tmp_path / "a.iq"), iq)
    with open_reader(p, sample_rate_hz=100_000, fmt="hackrf_int8") as r:
        assert r.sample_count == n
        chunk = r.read_chunk(0, 128)
        assert chunk.dtype == np.complex64
        assert chunk.size == 128
        assert np.isfinite(chunk).all()


def test_gqrx_fc32_reader(tmp_path):
    n = 512
    iq = np.exp(2j * np.pi * 0.01 * np.arange(n)).astype(np.complex64)
    interleaved = np.empty(n * 2, dtype="<f4")
    interleaved[0::2] = iq.real
    interleaved[1::2] = iq.imag
    p = tmp_path / "a.fc32"
    interleaved.tofile(p)
    with open_reader(str(p), sample_rate_hz=100_000) as r:
        assert r.name == "gqrx_fc32"
        out = r.read_chunk(0, n)
        assert np.allclose(out, iq, atol=1e-5)


def test_detect_format_fallback_hackrf(tmp_path):
    p = tmp_path / "x.iq"
    p.write_bytes(b"\x00" * 10)
    assert detect_format(str(p)) == "hackrf_int8"


def test_split_set_discovery_and_order(tmp_path):
    for i in range(3):
        iq = synth_4fsk(100, 100_000, 4800, 1800, seed=i)
        write_hackrf_int8(str(tmp_path / f"hackrf_{i:03d}.iq"), iq)
    ss = SplitSet.discover(str(tmp_path), sample_rate_hz=100_000,
                           fmt="hackrf_int8")
    assert ss.fmt == "hackrf_int8"
    assert len(ss.files) == 3
    assert ss.files == sorted(ss.files)
    # all 3 files are the same size ⇒ no gaps
    list(ss.iter_chunks(256))
    assert ss.gaps == []
    assert ss.total_samples == 300


def test_split_set_detects_gap(tmp_path):
    # Two full-sized files + one short middle file ⇒ gap recorded.
    full = synth_4fsk(200, 100_000, 4800, 1800, seed=0)
    short = synth_4fsk(100, 100_000, 4800, 1800, seed=1)
    write_hackrf_int8(str(tmp_path / "hackrf_0000.iq"), full)
    write_hackrf_int8(str(tmp_path / "hackrf_0001.iq"), short)
    write_hackrf_int8(str(tmp_path / "hackrf_0002.iq"), full)
    ss = SplitSet.discover(str(tmp_path), sample_rate_hz=100_000,
                           fmt="hackrf_int8")
    assert ss.expected_file_samples == 200
    list(ss.iter_chunks(256))
    assert len(ss.gaps) == 1
    assert ss.gaps[0].dropped_samples == 100


def test_sigmf_view_round_trip(tmp_path):
    iq = synth_4fsk(400, 1_000_000, 4800, 1800)
    write_hackrf_int8(str(tmp_path / "hackrf_0000.iq"), iq[:200])
    write_hackrf_int8(str(tmp_path / "hackrf_0001.iq"), iq[200:])
    ss = SplitSet.discover(str(tmp_path), sample_rate_hz=1_000_000,
                           fmt="hackrf_int8", center_hz=450e6)
    view = VirtualSigMF.from_split_set(ss)
    assert view.meta["global"]["core:sample_rate"] == 1_000_000.0
    assert len(view.meta["captures"]) == 2
    meta_path = write_view_meta(view, str(tmp_path / "out"))
    with open(meta_path) as fh:
        on_disk = json.load(fh)
    assert on_disk["global"]["wbdec:total_samples"] == 400
