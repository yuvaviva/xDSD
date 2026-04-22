"""Trunking parser + annotator + end-to-end run tests."""

from __future__ import annotations

import json
import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from wbdec.analyze.report import ChannelReport, Report
from wbdec.config import (
    CaptureConfig, ChannelizeConfig, Config, DecodeConfig, SurveyConfig,
)
from wbdec.encryption import EncryptionFinding
from wbdec.orchestrate.pipeline import run_pipeline
from wbdec.tests._synth import make_wideband_split_capture
from wbdec.trunking import (
    TrunkingEvent, attach_to_report, extract_dmr_events, extract_p25_events,
)
from wbdec.decode.dsd_fme import _parse_log


SHIM_TRUNK = textwrap.dedent(r"""
    #!{python}
    import argparse, sys, wave
    import numpy as np

    ap = argparse.ArgumentParser()
    ap.add_argument("-i", required=True)
    ap.add_argument("-w", required=True)
    args, _ = ap.parse_known_args()
    with wave.open(args.i, "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    pcm = np.frombuffer(raw, dtype="<i2")[::6].astype("<i2")
    with wave.open(args.w, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(8000)
        wf.writeframes(pcm.tobytes())
    print("Sync +P25p1 NAC: 0x293")
    print("HDU Algid: 0x80 Keyid: 0x0000 clear")
    print("LDU1 voice  TG: 1234  SRC: 567890")
    print("Group voice channel grant  TG: 4321 SRC: 999  freq: 851.1875 MHz  LCN: 0x05")
    print("LDU2 voice")
    """).strip()


def _write_shim(path: Path, script: str) -> None:
    path.write_text(script.format(python=sys.executable))
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


# ---------------------------------------------------------------------------
# log parser additions
# ---------------------------------------------------------------------------

def test_dsd_fme_log_extracts_trunking_fields():
    log = (
        "Sync +P25p1 NAC: 0x293\n"
        "Group voice channel grant TG: 4321 SRC: 999 freq: 851.1875 MHz LCN: 0x05\n"
        "LDU1 voice TG: 1234 SRC: 567890\n"
    )
    frames, nac, _algid, _keyid = _parse_log(log, duration_s=2.0)
    assert nac == 0x293
    types = [f.type for f in frames]
    assert "TRUNKING_GRANT" in types
    grant = next(f for f in frames if f.type == "TRUNKING_GRANT")
    assert grant.extras.get("talkgroup_id") == 4321
    assert grant.extras.get("source_id") == 999
    assert grant.extras.get("lcn") == 0x05
    assert abs(grant.extras.get("grant_freq_hz", 0) - 851.1875e6) < 1.0


# ---------------------------------------------------------------------------
# extractors
# ---------------------------------------------------------------------------

def test_p25_extractor_classifies_grant_vs_update():
    frames = [
        {"type": "TRUNKING_GRANT", "talkgroup_id": 100, "source_id": 200,
         "grant_freq_hz": 851_125_000, "lcn": 5, "t_offset_s": 0.5,
         "log_line": "grant"},
        {"type": "TRUNKING_INFO", "talkgroup_id": 100, "source_id": 200,
         "t_offset_s": 1.0, "log_line": "info"},
    ]
    evs = extract_p25_events("ev_test", nac_default=0x293, frames=frames)
    kinds = [e.kind for e in evs]
    assert "grant" in kinds
    assert any(e.protocol == "p25" for e in evs)
    assert evs[0].grant_freq_hz == 851_125_000


def test_dmr_extractor_runs_without_required_fields():
    frames = [{"type": "TRUNKING_INFO", "t_offset_s": 0.0, "log_line": "x"}]
    evs = extract_dmr_events("ev_dmr", nac_default=None, frames=frames)
    assert len(evs) == 1
    assert evs[0].protocol == "dmr"
    assert evs[0].kind == "info"


# ---------------------------------------------------------------------------
# annotator
# ---------------------------------------------------------------------------

def _ch(event_id: str, label: str, center_hz: float, t_start_s: float,
        frames_path: str | None = None, nac: int | None = None) -> ChannelReport:
    return ChannelReport(
        event_id=event_id, label=label, label_confidence=0.9,
        kind="continuous", center_hz=center_hz, bw_hz=12_500.0,
        snr_db=20.0, t_start_s=t_start_s, t_end_s=t_start_s + 4.0,
        duration_s=4.0, adapter="dsd_fme", decoded_ok=True,
        wav_path=None, frames_jsonl_path=frames_path,
        decode_error=None, frame_counts={}, nac=nac,
        encryption=EncryptionFinding(),
    )


def test_annotator_attaches_talkgroup_to_source_channel(tmp_path):
    frames_path = tmp_path / "control.jsonl"
    frames_path.write_text(
        json.dumps({"type": "TRUNKING_INFO", "talkgroup_id": 42,
                    "source_id": 9, "t_offset_s": 0.5,
                    "log_line": "TG 42 SRC 9"}) + "\n"
        + json.dumps({"type": "TRUNKING_GRANT", "talkgroup_id": 99,
                      "source_id": 9, "grant_freq_hz": 851_125_000.0,
                      "t_offset_s": 1.0, "log_line": "grant"}) + "\n"
    )
    control = _ch("ev_ctrl", "p25_c4fm", 851_000_000.0, 0.0, str(frames_path))
    voice = _ch("ev_voice", "p25_c4fm", 851_125_000.0, 1.5)
    bystander = _ch("ev_other", "p25_c4fm", 853_000_000.0, 1.5)

    report = Report(out_dir=str(tmp_path), capture_meta_path=None,
                    sample_rate_hz=10e6, center_hz=850e6, duration_s=10.0,
                    num_channels=3, num_decoded=3, num_encrypted=0,
                    channels=[control, voice, bystander])
    attach_to_report(report)

    assert control.talkgroup_id == 42      # picked up from update
    assert voice.talkgroup_id == 99        # matched to grant by freq+time
    assert bystander.talkgroup_id is None  # neither in source nor in grant
    assert voice.granted_by_event_id == "ev_ctrl"
    assert len(report.trunking_events) == 2


# ---------------------------------------------------------------------------
# end-to-end run with trunking content
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="shim uses POSIX shebang")
def test_run_pipeline_with_trunking(tmp_path):
    shim = tmp_path / "dsd-fme"
    _write_shim(shim, SHIM_TRUNK)
    folder = tmp_path / "iq"
    folder.mkdir()
    make_wideband_split_capture(
        str(folder), 1_000_000.0, 1.5,
        carriers=[("p25", +250_000.0, 0.4), ("dmr", -150_000.0, 0.4)],
        noise_rms=0.02, n_splits=2,
    )
    # Pre-write a survey.json with labels so the pipeline doesn't have to
    # hand-label. We do this by running the pipeline once, patching, and
    # reading. Simpler: write a config and use a custom invocation order.
    cfg = Config(
        capture=CaptureConfig(folder=str(folder), sample_rate_hz=1_000_000.0,
                              center_hz=850_000_000.0, format="hackrf_int8",
                              chunk_samples=1 << 17),
        survey=SurveyConfig(
            nperseg=2048, frame_samples=1 << 16,
            cfar_pfa=1e-4, min_bw_hz=2_000.0, max_bw_hz=40_000.0,
            min_persist_frames=1, max_absent_frames=1,
            burst_min_duty_cycle=0.1, burst_window_frames=4,
            merge_freq_tol_hz=6_250.0,
        ),
        channelize=ChannelizeConfig(out_dir="channels"),
        decode=DecodeConfig(out_dir="calls", dsd_fme_binary=str(shim), workers=1),
        out_dir=str(tmp_path / "out"),
    )
    # Manually run survey, label top-2, then re-invoke channelize+decode+analyze
    # via run_pipeline by deleting downstream artifacts. Easiest: hand-roll
    # the pipeline in this test.
    from wbdec.analyze.run import run_analyze
    from wbdec.channelize.run import run_channelize
    from wbdec.decode.run import run_decode
    from wbdec.survey.run import run_survey

    sv = run_survey(cfg)
    strong = sorted(sv.events, key=lambda e: -e.snr_db)[:2]
    if strong:
        strong[0].label = "p25_c4fm"
    if len(strong) > 1:
        strong[1].label = "dmr"
    sv.write_json(os.path.join(cfg.out_dir, "survey.json"))
    run_channelize(cfg)
    run_decode(cfg, workers=1)
    report = run_analyze(cfg)

    # Trunking events extracted from the shim's grant line.
    assert report.trunking_events, [c.frame_counts for c in report.channels]
    grant_events = [e for e in report.trunking_events if e.kind == "grant"]
    assert grant_events, [e.kind for e in report.trunking_events]
    grant = grant_events[0]
    assert grant.talkgroup_id == 4321
    assert abs((grant.grant_freq_hz or 0) - 851.1875e6) < 1.0

    # report.html mentions the talkgroup numerics.
    html_doc = (tmp_path / "out" / "report.html").read_text()
    assert "1234" in html_doc or "4321" in html_doc
    # Run-pipeline result counters look right (re-run from scratch).
    cfg2 = Config(**{**cfg.__dict__, "out_dir": str(tmp_path / "out2")})
    # Pre-label the new run too: relabel after survey inside run_pipeline.
    # (run_pipeline doesn't re-label — labels come from the survey classifier;
    #  the shim still parses log fields regardless of label.)
    res = run_pipeline(cfg2)
    assert res.channels >= 2
