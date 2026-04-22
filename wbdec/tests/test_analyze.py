"""Analyze-stage tests — aggregator, HTML + M3U, end-to-end."""

from __future__ import annotations

import json
import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from wbdec.analyze import (
    Report, aggregate, render_html, render_m3u, run_analyze,
)
from wbdec.analyze.report import ChannelReport
from wbdec.channelize.run import run_channelize
from wbdec.config import (
    CaptureConfig, ChannelizeConfig, Config, DecodeConfig, SurveyConfig,
)
from wbdec.decode import run_decode
from wbdec.encryption import EncryptionFinding
from wbdec.survey.run import run_survey
from wbdec.tests._synth import make_wideband_split_capture


# Same shim used in test_decode.
SHIM_AES = textwrap.dedent(r"""
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
    print("HDU Algid: 0x84 Keyid: 0x1234 encrypted")
    print("LDU1 voice")
    print("LDU2 voice")
    """).strip()

SHIM_CLEAR = textwrap.dedent(r"""
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
    print("LDU1 voice")
    """).strip()


def _write_shim(path: Path, script: str) -> None:
    path.write_text(script.format(python=sys.executable))
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


# ---------------------------------------------------------------------------
# Aggregator (fast, fabricate on-disk artifacts)
# ---------------------------------------------------------------------------

def _fabricate_run(tmp_path: Path,
                   *, algid: int | None, keyid: int | None) -> Path:
    """Construct the on-disk file tree that aggregate() expects."""
    out = tmp_path / "out"
    out.mkdir()
    (out / "channels").mkdir()
    (out / "calls").mkdir()
    (out / "frames").mkdir()

    # survey.json
    (out / "survey.json").write_text(json.dumps({
        "capture_meta_path": str(out / "capture.sigmf-meta"),
        "sample_rate_hz": 10e6, "center_hz": 450e6,
        "duration_s": 10.0, "num_frames": 100, "frame_period_s": 0.1,
        "events": [{
            "event_id": "ev_test", "label": "p25_c4fm",
            "label_confidence": 0.9, "kind": "continuous",
            "center_hz": 450_250_000, "bw_hz": 12_500,
            "snr_db": 22.0, "t_start_s": 1.0, "t_end_s": 5.0,
            "peak_power_db": -30, "hits": 40, "duty_cycle": 1.0,
        }],
        "gaps": [],
    }))

    # channel meta
    (out / "channels" / "ev_test.sigmf-meta").write_text(json.dumps({
        "global": {
            "core:datatype": "cf32_le", "core:sample_rate": 50000.0,
            "wbdec:event_id": "ev_test",
            "wbdec:label": "p25_c4fm",
            "wbdec:label_confidence": 0.9,
            "wbdec:channel_bw_hz": 12500.0,
            "wbdec:demod_hint": "fm", "wbdec:rrc_applied": False,
        },
        "captures": [{"core:sample_start": 0,
                      "core:frequency": 450_250_000,
                      "wbdec:t_start_s": 1.0, "wbdec:t_end_s": 5.0}],
        "annotations": [],
    }))
    # tiny fake data so the path is real
    (out / "channels" / "ev_test.sigmf-data").write_bytes(b"\x00" * 8)

    # frames
    frames_jsonl = out / "frames" / "ev_test.jsonl"
    frame = {"t_offset_s": 0.5, "type": "P25_HDU"}
    if algid is not None:
        frame["algid"] = algid
    if keyid is not None:
        frame["keyid"] = keyid
    frames_jsonl.write_text(json.dumps(frame) + "\n"
                            + json.dumps({"t_offset_s": 1.0, "type": "P25_LDU1"})
                            + "\n")

    # decode.json
    wav_path = str(out / "calls" / "ev_test.wav")
    Path(wav_path).write_bytes(b"RIFF")  # dummy; HTML doesn't verify content
    (out / "decode.json").write_text(json.dumps({
        "num_channels": 1, "num_decoded": 1, "num_skipped": 0,
        "results": {
            "ev_test": {
                "event_id": "ev_test", "protocol": "p25_c4fm",
                "adapter": "dsd_fme", "ok": True,
                "pcm_wav_path": wav_path,
                "frames_jsonl_path": str(frames_jsonl),
                "nac": 0x293, "algid": algid, "keyid": keyid,
                "duration_s": 4.0, "n_frames": 2,
                "error": None, "extras": {},
            }
        },
        "skipped": [],
    }))
    return out


def test_aggregate_clear_channel(tmp_path):
    out = _fabricate_run(tmp_path, algid=0x80, keyid=0x0)
    r = aggregate(str(out))
    assert r.num_channels == 1
    assert r.num_decoded == 1
    assert r.num_encrypted == 0
    c = r.channels[0]
    assert c.label == "p25_c4fm"
    assert c.nac == 0x293
    assert c.encryption.encrypted is False


def test_aggregate_encrypted_channel(tmp_path):
    out = _fabricate_run(tmp_path, algid=0x84, keyid=0x1234)
    r = aggregate(str(out))
    assert r.num_encrypted == 1
    c = r.channels[0]
    assert c.encryption.encrypted
    assert c.encryption.algorithm == "AES-256"
    assert c.encryption.key_id == 0x1234


# ---------------------------------------------------------------------------
# HTML + M3U
# ---------------------------------------------------------------------------

def _make_report_one(enc: bool) -> Report:
    finding = (EncryptionFinding(encrypted=True, algorithm="AES-256",
                                 algorithm_id=0x84, key_id=0x1234,
                                 evidence=["algid=0x84"])
               if enc else EncryptionFinding())
    c = ChannelReport(
        event_id="ev_test", label="p25_c4fm", label_confidence=0.9,
        kind="continuous", center_hz=450_250_000.0, bw_hz=12500.0,
        snr_db=22.0, t_start_s=1.0, t_end_s=5.0, duration_s=4.0,
        adapter="dsd_fme", decoded_ok=True,
        wav_path="/tmp/out/calls/ev_test.wav",
        frames_jsonl_path="/tmp/out/frames/ev_test.jsonl",
        decode_error=None,
        frame_counts={"P25_HDU": 1, "P25_LDU1": 1},
        nac=0x293, encryption=finding,
    )
    return Report(out_dir="/tmp/out", capture_meta_path=None,
                  sample_rate_hz=10e6, center_hz=450e6, duration_s=10.0,
                  num_channels=1, num_decoded=1,
                  num_encrypted=1 if enc else 0, channels=[c])


def test_render_html_valid_structure():
    r = _make_report_one(enc=True)
    html_doc = render_html(r)
    assert "<!doctype html>" in html_doc.lower()
    assert "wbdec capture report" in html_doc
    assert "AES-256" in html_doc
    assert "ev_test" in html_doc
    assert "<audio controls" in html_doc
    assert "0x293" in html_doc


def test_render_html_clear_channel():
    r = _make_report_one(enc=False)
    html_doc = render_html(r)
    assert "clear</span>" in html_doc.lower()
    assert "aes-256" not in html_doc.lower()


def test_render_m3u():
    r = _make_report_one(enc=True)
    m3u = render_m3u(r)
    assert m3u.startswith("#EXTM3U")
    assert "#EXTINF" in m3u
    assert "calls/ev_test.wav" in m3u
    assert "AES-256" in m3u


# ---------------------------------------------------------------------------
# End-to-end 5-stage pipeline with a shim
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="shim uses POSIX shebang")
def test_pipeline_all_five_stages(tmp_path):
    shim = tmp_path / "dsd-fme"
    _write_shim(shim, SHIM_AES)
    folder = tmp_path / "iq"
    folder.mkdir()
    make_wideband_split_capture(
        str(folder), 1_000_000.0, 1.5,
        carriers=[("p25", +250_000.0, 0.4), ("dmr", -150_000.0, 0.4)],
        noise_rms=0.02, n_splits=2,
    )
    cfg = Config(
        capture=CaptureConfig(folder=str(folder), sample_rate_hz=1_000_000.0,
                              center_hz=450e6, format="hackrf_int8",
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
    sv = run_survey(cfg)
    # Label the top 2 events for the decoder to pick them up.
    strong = sorted(sv.events, key=lambda e: -e.snr_db)[:2]
    strong[0].label = "p25_c4fm"
    if len(strong) > 1:
        strong[1].label = "dmr"
    # Re-persist survey.json with labels.
    sv.write_json(os.path.join(cfg.out_dir, "survey.json"))
    run_channelize(cfg)
    run_decode(cfg, workers=1)
    report = run_analyze(cfg)

    # Every strong event that decoded should show up with encryption flagged.
    # P25 maps 0x84 → "AES-256"; DMR maps 0x84 → "AES" — both are encrypted.
    encrypted_events = [c for c in report.channels if c.encryption.encrypted]
    assert len(encrypted_events) >= 2, [
        {"id": c.event_id, "label": c.label, "enc": c.encryption.encrypted}
        for c in report.channels]
    algs = {c.encryption.algorithm for c in encrypted_events}
    assert algs & {"AES", "AES-256"}, algs

    # Artifacts on disk.
    assert (tmp_path / "out" / "report.json").exists()
    assert (tmp_path / "out" / "report.html").exists()
    assert (tmp_path / "out" / "calls" / "index.m3u").exists()
    html_doc = (tmp_path / "out" / "report.html").read_text()
    assert "AES-256" in html_doc
