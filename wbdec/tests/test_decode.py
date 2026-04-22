"""Decode-stage tests.

Uses a Python shim as a stand-in for ``dsd-fme`` so the tests run on any
machine without requiring a real binary. The shim accepts the real DSD CLI
flags, reads the input WAV, writes an output WAV, and prints log lines that
exercise the field-parser (NAC / algid / keyid / HDU / LDU).
"""

from __future__ import annotations

import json
import os
import stat
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest

from wbdec.config import (
    CaptureConfig, ChannelizeConfig, Config, DecodeConfig, SurveyConfig,
)
from wbdec.channelize.run import run_channelize
from wbdec.decode import (
    DecodeOptions, DsdFmeAdapter, GrDsdAdapter, TetraRxAdapter,
    TetraNativeAdapter, run_decode,
)
from wbdec.decode.dsd_fme import _parse_log
from wbdec.decode.registry import (
    all_adapters, get_adapter_by_name, get_adapters_for,
)
from wbdec.demod import fm_discriminator
from wbdec.survey.run import run_survey
from wbdec.tests._synth import make_wideband_split_capture


SHIM = textwrap.dedent(r"""
    #!{python}
    import argparse, os, sys, wave
    import numpy as np

    ap = argparse.ArgumentParser()
    ap.add_argument("-i", required=True)
    ap.add_argument("-w", required=True)
    mode = None
    for a in sys.argv[1:]:
        if a.startswith("-f") and len(a) >= 3:
            mode = a[2:]
    args, _ = ap.parse_known_args()

    print(f"DSD shim: mode=-f{{mode}}")
    with wave.open(args.i, "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    pcm = np.frombuffer(raw, dtype="<i2")
    out = pcm[::6].astype("<i2")
    with wave.open(args.w, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(out.tobytes())
    print("Sync +P25p1 NAC: 0x293")
    print("HDU Algid: 0x84  Keyid: 0x1234  (encryption enabled)")
    print("LDU1 voice")
    print("LDU2 voice")
    """).strip()


def _write_shim(path: Path) -> None:
    path.write_text(SHIM.format(python=sys.executable))
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_registry_contains_builtins():
    names = {cls.name for cls in all_adapters()}
    assert {"dsd_fme", "gr_dsd", "tetra_rx", "tetra_native"} <= names


def test_get_adapters_for_p25():
    candidates = get_adapters_for("p25_c4fm", demod_hint="fm")
    names = [c.name for c in candidates]
    assert "dsd_fme" in names
    assert "gr_dsd" in names


def test_get_adapters_for_tetra():
    candidates = get_adapters_for("tetra", demod_hint="linear")
    names = {c.name for c in candidates}
    assert {"tetra_rx", "tetra_native"} <= names


# ---------------------------------------------------------------------------
# dsd-fme log parser
# ---------------------------------------------------------------------------

def test_log_parser_extracts_fields():
    log = (
        "boot\nSync: +P25p1  NAC: 0x293\n"
        "HDU Algid: 0x84 Keyid: 0x1234  encrypted\n"
        "LDU1 voice\n"
        "LDU2 voice\n"
    )
    frames, nac, algid, keyid = _parse_log(log, duration_s=2.0)
    assert nac == 0x293
    assert algid == 0x84
    assert keyid == 0x1234
    types = {f.type for f in frames}
    assert "P25_HDU" in types
    assert any(t.startswith("P25_LDU") for t in types)


# ---------------------------------------------------------------------------
# Adapter availability
# ---------------------------------------------------------------------------

def test_gr_dsd_unavailable_when_swig_missing():
    # Default environment has no compiled dsd; adapter should degrade.
    assert GrDsdAdapter().is_available() is False


# ---------------------------------------------------------------------------
# dsd_fme adapter against the shim
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32",
                    reason="shim uses POSIX shebang")
def test_dsd_fme_adapter_with_shim(tmp_path):
    shim = tmp_path / "dsd-fme"
    _write_shim(shim)

    # Fabricate a plausible cf32 channel file + meta.
    chdir = tmp_path / "channels"
    chdir.mkdir()
    fs = 50_000.0
    n = int(2.0 * fs)
    t = np.arange(n) / fs
    iq = (0.5 * np.exp(2j * np.pi * 1000 * t) * np.exp(
        1j * 0.3 * np.sin(2 * np.pi * 3.0 * t))).astype(np.complex64)
    data = chdir / "evc_000000.sigmf-data"
    interleaved = np.empty(iq.size * 2, dtype="<f4")
    interleaved[0::2] = iq.real
    interleaved[1::2] = iq.imag
    data.write_bytes(interleaved.tobytes())
    meta = chdir / "evc_000000.sigmf-meta"
    meta.write_text(json.dumps({
        "global": {
            "core:datatype": "cf32_le",
            "core:sample_rate": fs,
            "wbdec:event_id": "evc_000000",
            "wbdec:label": "p25_c4fm",
            "wbdec:demod_hint": "fm",
            "wbdec:rrc_applied": False,
        },
        "captures": [{"core:sample_start": 0, "core:frequency": 450e6}],
        "annotations": [],
    }))

    opts = DecodeOptions(
        out_dir=str(tmp_path / "out"),
        dsd_fme_binary=str(shim), timeout_s=30.0,
    )
    res = DsdFmeAdapter().decode(str(meta), opts)
    assert res.ok, res.error
    assert res.protocol == "p25_c4fm"
    assert res.adapter == "dsd_fme"
    assert res.pcm_wav_path and os.path.exists(res.pcm_wav_path)
    assert res.frames_jsonl_path and os.path.exists(res.frames_jsonl_path)
    assert res.nac == 0x293
    assert res.algid == 0x84
    assert res.keyid == 0x1234
    assert res.n_frames >= 3


@pytest.mark.skipif(sys.platform == "win32",
                    reason="shim uses POSIX shebang")
def test_run_decode_end_to_end_with_shim(tmp_path):
    shim = tmp_path / "dsd-fme"
    _write_shim(shim)
    folder = tmp_path / "iq"
    folder.mkdir()
    make_wideband_split_capture(
        str(folder), 1_000_000.0, 1.5,
        carriers=[("p25", +250_000.0, 0.4), ("dmr", -150_000.0, 0.4)],
        noise_rms=0.02, n_splits=2,
    )
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
        decode=DecodeConfig(
            out_dir="calls", dsd_fme_binary=str(shim), workers=1),
        out_dir=str(tmp_path / "out"),
    )
    sv = run_survey(cfg)
    # Attach labels so the orchestrator knows which adapter to pick.
    for ev in sv.events:
        # assign crudely by offset
        if ev.center_hz > 0:
            ev.label = "p25_c4fm"
        else:
            ev.label = "dmr"
    # Rewrite survey.json with labels.
    from wbdec.survey.schema import SurveyResult
    result = SurveyResult(
        capture_meta_path=sv.capture_meta_path,
        sample_rate_hz=sv.sample_rate_hz, center_hz=sv.center_hz,
        duration_s=sv.duration_s, num_frames=sv.num_frames,
        frame_period_s=sv.frame_period_s, events=sv.events, gaps=sv.gaps,
    )
    result.write_json(os.path.join(cfg.out_dir, "survey.json"))

    run_channelize(cfg)
    summary = run_decode(cfg, workers=1)
    assert summary["num_channels"] >= 2
    assert summary["num_decoded"] >= 2
    for r in summary["results"].values():
        if not r["ok"]:
            continue
        assert r["adapter"] == "dsd_fme"
        assert r["nac"] == 0x293
        assert r["algid"] == 0x84
        assert r["keyid"] == 0x1234
        assert os.path.exists(r["pcm_wav_path"])
        assert os.path.exists(r["frames_jsonl_path"])


# ---------------------------------------------------------------------------
# tetra_native smoke
# ---------------------------------------------------------------------------

def test_tetra_native_emits_frames_without_voice(tmp_path):
    # Build a synthetic RRC-matched-ish TETRA baseband: π/4-DQPSK constellation.
    fs = 72_000.0
    from wbdec.tests._synth import synth_pi4_dqpsk
    iq = synth_pi4_dqpsk(1 << 15, fs, 18_000, seed=3)

    chdir = tmp_path / "channels"
    chdir.mkdir()
    data = chdir / "evb_000000.sigmf-data"
    interleaved = np.empty(iq.size * 2, dtype="<f4")
    interleaved[0::2] = iq.real
    interleaved[1::2] = iq.imag
    data.write_bytes(interleaved.tobytes())
    meta = chdir / "evb_000000.sigmf-meta"
    meta.write_text(json.dumps({
        "global": {
            "core:datatype": "cf32_le",
            "core:sample_rate": fs,
            "wbdec:event_id": "evb_000000",
            "wbdec:label": "tetra",
            "wbdec:demod_hint": "linear",
            "wbdec:rrc_applied": True,
        },
        "captures": [{"core:sample_start": 0, "core:frequency": 390e6}],
        "annotations": [],
    }))
    opts = DecodeOptions(out_dir=str(tmp_path / "out"))
    res = TetraNativeAdapter().decode(str(meta), opts)
    # Synthetic isn't a real TETRA signal; what we verify is the adapter's
    # contract: always-returns-result, emits frames.jsonl, never raises.
    assert res.adapter == "tetra_native"
    assert res.frames_jsonl_path and os.path.exists(res.frames_jsonl_path)
    assert res.error is not None   # "no audio produced" is expected


def test_tetra_rx_unavailable_gracefully(tmp_path):
    """When tetra-rx is not on PATH, the adapter returns ok=False, doesn't raise."""
    chdir = tmp_path / "channels"
    chdir.mkdir()
    data = chdir / "evb_0.sigmf-data"
    data.write_bytes(b"\x00" * 32)
    meta = chdir / "evb_0.sigmf-meta"
    meta.write_text(json.dumps({
        "global": {
            "core:sample_rate": 72_000.0, "core:datatype": "cf32_le",
            "wbdec:label": "tetra", "wbdec:event_id": "evb_0",
            "wbdec:demod_hint": "linear", "wbdec:rrc_applied": True,
        },
        "captures": [{"core:sample_start": 0, "core:frequency": 0.0}],
        "annotations": [],
    }))
    opts = DecodeOptions(
        out_dir=str(tmp_path / "out"),
        tetra_rx_binary="definitely-not-tetra-rx-xyz",
    )
    res = TetraRxAdapter().decode(str(meta), opts)
    assert res.ok is False
    assert "not on PATH" in (res.error or "")
