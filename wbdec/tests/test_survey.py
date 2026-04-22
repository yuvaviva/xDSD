"""Survey tests: PSD + CFAR + trackers + run_survey end-to-end."""

from __future__ import annotations

import json
import os

import numpy as np

from wbdec.config import CaptureConfig, Config, SurveyConfig
from wbdec.survey.cfar import ca_cfar_mask, group_peaks
from wbdec.survey.psd_stream import freq_axis, welch_frame
from wbdec.survey.tracker_burst import BurstTracker
from wbdec.survey.tracker_continuous import ContinuousTracker
from wbdec.survey.run import run_survey
from wbdec.tests._synth import make_wideband_split_capture


def test_welch_produces_peak_at_carrier():
    fs = 1_000_000.0
    t = np.arange(1 << 14) / fs
    sig = (0.5 * np.exp(2j * np.pi * 125_000 * t)).astype(np.complex64)
    psd = welch_frame(sig, 2048, 0.5)
    f = freq_axis(2048, fs)
    peak = int(np.argmax(psd))
    assert abs(f[peak] - 125_000) < fs / 2048


def test_cfar_empty():
    psd = np.full(1024, 1e-12, dtype=np.float32)
    m = ca_cfar_mask(psd, 4, 32, 1e-4)
    assert not m.any()


def test_cfar_single_tone():
    fs = 500_000.0
    n = 1 << 14
    t = np.arange(n) / fs
    noise = 0.01 * (np.random.default_rng(0).standard_normal(n)
                    + 1j * np.random.default_rng(1).standard_normal(n))
    sig = (0.3 * np.exp(2j * np.pi * 100_000 * t)) + noise
    psd = welch_frame(sig.astype(np.complex64), 1024, 0.5)
    mask = ca_cfar_mask(psd, 4, 32, 1e-6)
    freqs = freq_axis(1024, fs)
    groups = group_peaks(mask, freqs, psd, min_bw_bins=1)
    assert any(abs(g[2] - 100_000) < fs / 1024 * 2 for g in groups)


def test_continuous_tracker_promotes_persistent_track():
    trk = ContinuousTracker(frame_period_s=0.01, min_persist_frames=2,
                            max_absent_frames=1, merge_tol_hz=5_000)
    for i in range(5):
        trk.update(i, [(450_012_500.0, 12_500.0, 1.0, 0.01)])
    trk.flush()
    ev = trk.events()
    assert len(ev) == 1
    assert abs(ev[0].center_hz - 450_012_500.0) < 1.0
    assert ev[0].kind == "continuous"
    assert ev[0].snr_db > 10


def test_burst_tracker_flags_bursty_channel():
    trk = BurstTracker(frame_period_s=0.01, window_frames=8,
                       min_duty_cycle=0.2, merge_tol_hz=6_250,
                       min_bursts=3)
    # 3/8 duty in window — should register as burst.
    hits = [0, 3, 6, 11, 14, 17]
    for f in range(20):
        det = []
        if f in hits:
            det = [(450_012_500.0, 12_500.0, 1.0, 0.01)]
        trk.update(f, det)
    trk.flush()
    ev = trk.events()
    assert any(e.kind == "burst" and abs(e.center_hz - 450_012_500.0) < 10.0
               for e in ev)


def test_run_survey_end_to_end(tmp_path):
    folder = tmp_path / "iq"
    folder.mkdir()
    sample_rate = 1_000_000.0
    make_wideband_split_capture(
        str(folder), sample_rate_hz=sample_rate, duration_s=1.0,
        carriers=[
            ("p25",  +250_000.0, 0.4),
            ("dmr",  -150_000.0, 0.4),  # bursty in the synth
        ],
        noise_rms=0.02, seed=1, n_splits=2,
    )
    cfg = Config(
        capture=CaptureConfig(
            folder=str(folder), sample_rate_hz=sample_rate, center_hz=0.0,
            format="hackrf_int8", chunk_samples=1 << 18),
        survey=SurveyConfig(
            nperseg=2048, frame_samples=1 << 16,
            cfar_guard=4, cfar_train=32, cfar_pfa=1e-4,
            min_bw_hz=2_000.0, max_bw_hz=40_000.0,
            min_persist_frames=1, max_absent_frames=1,
            burst_min_duty_cycle=0.1, burst_window_frames=4,
            merge_freq_tol_hz=6_250.0,
        ),
        out_dir=str(tmp_path / "out"),
    )
    result = run_survey(cfg)
    centers = [ev.center_hz for ev in result.events]
    assert any(abs(c - 250_000) < 15_000 for c in centers), centers
    assert any(abs(c + 150_000) < 15_000 for c in centers), centers
    # Report written.
    sjson = tmp_path / "out" / "survey.json"
    assert sjson.exists()
    data = json.loads(sjson.read_text())
    assert data["num_frames"] > 0
    assert len(data["events"]) == len(result.events)
    assert data["capture_meta_path"].endswith(".sigmf-meta")
