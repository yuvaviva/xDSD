"""Channelize tests: grid, RRC, extractor round-trip, run_channelize e2e."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

from wbdec.channelize.extractor import ChannelExtractor, ExtractorConfig
from wbdec.channelize.grid import TARGETS, target_for_label, choose_decimation
from wbdec.channelize.rrc import rrc_taps
from wbdec.channelize.run import run_channelize
from wbdec.config import CaptureConfig, ChannelizeConfig, Config, SurveyConfig
from wbdec.survey.run import run_survey
from wbdec.tests._synth import make_wideband_split_capture


# ---------------------------------------------------------------------------
# grid
# ---------------------------------------------------------------------------

def test_target_lookup_and_fallback():
    assert target_for_label("p25_c4fm").out_rate_hz == 48_000.0
    assert target_for_label("tetra").apply_rrc
    assert target_for_label(None).label == "unknown"
    assert target_for_label("nonsense").label == "unknown"


def test_choose_decimation_monotone():
    assert choose_decimation(1_000_000, 48_000) >= 1
    assert choose_decimation(1_000_000, 48_000) == 1_000_000 // 48_000


# ---------------------------------------------------------------------------
# RRC
# ---------------------------------------------------------------------------

def test_rrc_unit_energy_and_odd_length():
    h = rrc_taps(72_000.0, 18_000.0, rolloff=0.35, num_symbols=8)
    assert h.dtype == np.float32
    assert h.size % 2 == 1
    assert abs(float(np.sum(h ** 2)) - 1.0) < 1e-5


# ---------------------------------------------------------------------------
# extractor
# ---------------------------------------------------------------------------

def test_extractor_recovers_tone_at_dc(tmp_path):
    """A pure tone at +125 kHz in a 1 Msps source, extracted at offset +125 kHz,
    should land at ~DC in the output.
    """
    fs = 1_000_000.0
    n = 1 << 17
    t = np.arange(n) / fs
    src = np.exp(2j * np.pi * 125_000 * t).astype(np.complex64)
    cfg = ExtractorConfig(
        event_id="ev_test", center_offset_hz=125_000.0,
        source_rate_hz=fs, target=target_for_label("p25_c4fm"),
        t_start_s=0.0, t_end_s=1.0,
    )
    out: list[np.ndarray] = []
    ext = ChannelExtractor(cfg, on_samples=lambda s: out.append(s))
    # Push as two chunks to exercise state preservation.
    ext.push_chunk(src[: n // 2], 0.0)
    ext.push_chunk(src[n // 2:], (n // 2) / fs)
    joined = np.concatenate(out)
    assert joined.size > 0
    # FFT the tail (skip LPF transient) and assert the peak is near DC.
    tail = joined[ext.lpf_taps.size:]
    assert tail.size > 1024, tail.size
    spec = np.fft.fftshift(np.fft.fft(tail[:4096] * np.hanning(4096)))
    f_axis = np.fft.fftshift(np.fft.fftfreq(4096, 1.0 / ext.out_rate_hz))
    peak = int(np.argmax(np.abs(spec)))
    # Within 1 bin of DC:
    bin_hz = ext.out_rate_hz / 4096
    assert abs(f_axis[peak]) <= bin_hz * 1.5, (f_axis[peak], bin_hz)


def test_extractor_preserves_phase_across_chunks():
    """Running the extractor in one shot vs many small pieces should give
    the same output samples (up to float tolerance) — otherwise state is
    being dropped between chunks.
    """
    fs = 500_000.0
    n = 1 << 15
    t = np.arange(n) / fs
    src = (0.5 * np.exp(2j * np.pi * 60_000 * t)).astype(np.complex64)
    tgt = TARGETS["p25_c4fm"]
    cfg = ExtractorConfig("ev", 60_000.0, fs, tgt, 0.0, 1.0)

    ref_out: list[np.ndarray] = []
    ref = ChannelExtractor(cfg, on_samples=lambda s: ref_out.append(s))
    ref.push_chunk(src, 0.0)
    ref_joined = np.concatenate(ref_out)

    chunked_out: list[np.ndarray] = []
    chunked = ChannelExtractor(cfg, on_samples=lambda s: chunked_out.append(s))
    step = 1111
    for a in range(0, n, step):
        b = min(a + step, n)
        chunked.push_chunk(src[a:b], a / fs)
    chunked_joined = np.concatenate(chunked_out)

    # Output sizes match exactly (within 1 sample due to LPF boundary).
    assert abs(ref_joined.size - chunked_joined.size) <= 1
    m = min(ref_joined.size, chunked_joined.size)
    # Beyond the LPF transient, samples must match within float noise.
    lead = 512
    diff = np.abs(ref_joined[lead:m] - chunked_joined[lead:m])
    assert float(np.median(diff)) < 1e-4, float(np.median(diff))


# ---------------------------------------------------------------------------
# run_channelize end-to-end
# ---------------------------------------------------------------------------

def test_run_channelize_e2e(tmp_path):
    folder = tmp_path / "iq"
    folder.mkdir()
    make_wideband_split_capture(
        str(folder), 1_000_000.0, 1.5,
        carriers=[
            ("p25", +250_000.0, 0.4),
            ("dmr", -150_000.0, 0.4),
        ],
        noise_rms=0.02, n_splits=3,
    )
    out = tmp_path / "out"
    cfg = Config(
        capture=CaptureConfig(
            folder=str(folder), sample_rate_hz=1_000_000.0, center_hz=0.0,
            format="hackrf_int8", chunk_samples=1 << 17),
        survey=SurveyConfig(
            nperseg=2048, frame_samples=1 << 16,
            cfar_pfa=1e-4, min_bw_hz=2_000.0, max_bw_hz=40_000.0,
            min_persist_frames=1, max_absent_frames=1,
            burst_min_duty_cycle=0.1, burst_window_frames=4,
            merge_freq_tol_hz=6_250.0,
        ),
        channelize=ChannelizeConfig(out_dir="channels"),
        out_dir=str(out),
    )
    sv = run_survey(cfg)
    assert len(sv.events) >= 2

    metas = run_channelize(cfg)
    assert len(metas) == len(sv.events)

    # For each strong event, load its channel file and verify DC peak.
    chdir = out / "channels"
    strong = [e for e in sv.events if e.snr_db > 12.0]
    assert strong
    for ev in strong:
        meta_path = chdir / f"{ev.event_id}.sigmf-meta"
        data_path = chdir / f"{ev.event_id}.sigmf-data"
        assert meta_path.exists() and data_path.exists()
        meta = json.loads(meta_path.read_text())
        fs_out = meta["global"]["core:sample_rate"]
        raw = np.fromfile(str(data_path), dtype="<f4")
        iq = (raw[0::2] + 1j * raw[1::2]).astype(np.complex64)
        # Skip the LPF transient.
        lead = 512
        assert iq.size > lead + 4096, iq.size
        seg = iq[lead: lead + 4096] * np.hanning(4096)
        spec = np.fft.fftshift(np.fft.fft(seg))
        f_axis = np.fft.fftshift(np.fft.fftfreq(4096, 1.0 / fs_out))
        peak = int(np.argmax(np.abs(spec)))
        # Peak should be within a few kHz of DC after channelization.
        assert abs(f_axis[peak]) < 5_000.0, (ev.event_id, f_axis[peak], fs_out)
