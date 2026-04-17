"""End-to-end synthesis test of the full pipeline.

Generates a small wideband IQ capture (HackRF int8) with two 4FSK carriers
offset to +/- a few hundred kHz, runs the pipeline, asserts detection and
classification succeed. The actual dsd decode is skipped gracefully when the
GNU Radio block is not importable, so this test is CI-friendly.
"""

from __future__ import annotations

import os

import numpy as np

from dsd.wideband import run_job
from dsd.wideband.config import (
    WidebandConfig,
    IngestConfig,
    DetectConfig,
    OutputConfig,
    DecodeConfig,
)
from dsd.wideband.tests._synth import make_wideband_capture


def test_end_to_end_two_carriers(tmp_path):
    folder = tmp_path / "iq"
    folder.mkdir()
    sample_rate = 1_000_000.0   # 1 Msps for a fast test
    out_dir = tmp_path / "out"
    make_wideband_capture(
        str(folder / "hackrf_0001.iq"),
        sample_rate=sample_rate, duration_s=1.0,
        carriers=[("p25", +250_000.0, 0.4),
                  ("dmr", -150_000.0, 0.4)],
        noise_rms=0.02,
    )
    cfg = WidebandConfig(
        ingest=IngestConfig(folder=str(folder), sample_rate=sample_rate,
                            center_hz=0.0, format="hackrf_int8"),
        detect=DetectConfig(nperseg=2048, nav=8, cfar_guard=4, cfar_train=32,
                            cfar_pfa=1e-4, min_bw_hz=2_000.0,
                            max_bw_hz=40_000.0, min_persist_frames=1,
                            max_absent_frames=1),
        decode=DecodeConfig(enable_p25=True, enable_dmr=True,
                            enable_tetra=False, enable_dpmr=False, workers=1),
        output=OutputConfig(out_dir=str(out_dir), write_wav=False,
                            write_spectrogram_png=False),
    )
    report = run_job(cfg)
    assert report["num_events"] >= 2, report
    centers = [ev["event"]["center_hz"] for ev in report["events"]]
    assert any(abs(c - 250_000) < 20_000 for c in centers), centers
    assert any(abs(c + 150_000) < 20_000 for c in centers), centers
    labels = [ev["event"]["label"] for ev in report["events"]]
    assert all(l in ("p25_c4fm", "dmr", "dpmr", "tetra", "unknown")
               for l in labels)
