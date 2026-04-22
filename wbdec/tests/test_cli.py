"""Smoke tests for the CLI."""

from __future__ import annotations

import json
import os

from wbdec.cli import main
from wbdec.tests._synth import make_wideband_split_capture


def test_cli_ingest(tmp_path, capsys):
    folder = tmp_path / "iq"
    folder.mkdir()
    make_wideband_split_capture(str(folder), 1_000_000.0, 0.2,
                                [("p25", 50_000.0, 0.4)], n_splits=2)
    rc = main(["ingest", str(folder),
               "--sample-rate", "1e6",
               "--format", "hackrf_int8",
               "--out", str(tmp_path / "out")])
    assert rc == 0
    manifest = tmp_path / "out" / "ingest_manifest.json"
    assert manifest.exists()
    data = json.loads(manifest.read_text())
    assert data["format"] == "hackrf_int8"
    assert len(data["files"]) == 2
    assert data["total_samples"] == 200_000


def test_cli_survey(tmp_path):
    folder = tmp_path / "iq"
    folder.mkdir()
    make_wideband_split_capture(str(folder), 1_000_000.0, 1.0,
                                [("p25", 250_000.0, 0.4),
                                 ("dmr", -150_000.0, 0.4)],
                                noise_rms=0.02, n_splits=2)
    # Default SurveyConfig assumes 10 Msps / multi-second captures; for a
    # 1-second test we need smaller frames. Write a config file.
    cfg = {
        "capture": {
            "folder": str(folder),
            "sample_rate_hz": 1_000_000.0,
            "center_hz": 0.0,
            "format": "hackrf_int8",
            "chunk_samples": 1 << 17,
        },
        "survey": {
            "nperseg": 2048,
            "frame_samples": 1 << 16,
            "cfar_guard": 4,
            "cfar_train": 32,
            "cfar_pfa": 0.0001,
            "min_bw_hz": 2000.0,
            "max_bw_hz": 40000.0,
            "min_persist_frames": 1,
            "max_absent_frames": 1,
            "burst_min_duty_cycle": 0.1,
            "burst_window_frames": 4,
            "merge_freq_tol_hz": 6250.0,
        },
    }
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg))
    out = tmp_path / "out"
    rc = main(["survey", "--config", str(cfg_path), "--out", str(out)])
    assert rc == 0
    sv = out / "survey.json"
    assert sv.exists()
    data = json.loads(sv.read_text())
    assert data["num_frames"] > 0
    assert len(data["events"]) >= 2
