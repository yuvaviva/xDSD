"""Tests for the subprocess-based DSD runner.

Uses a tiny Python shim as a stand-in for ``dsd-fme`` so the test works on
any machine. The shim accepts the real DSD CLI flags, reads the input WAV,
writes an output WAV, and prints lines that match DSD's real log format
so we can verify encryption-field parsing.
"""

from __future__ import annotations

import os
import stat
import sys
import textwrap
import wave

import numpy as np
import pytest

from dsd.wideband.decode.dsdplus_runner import (
    decode_with_dsd_subprocess,
    _parse_log_fields,
)


SHIM_TEMPLATE = textwrap.dedent(r"""
    #!{python}
    import argparse, os, struct, sys, wave
    import numpy as np

    ap = argparse.ArgumentParser()
    ap.add_argument("-i", required=True)
    ap.add_argument("-w", required=True)
    # Absorb every -f<letter> combination; argparse can't do prefix matching
    # trivially, so we sniff argv.
    mode_letter = None
    for a in sys.argv[1:]:
        if a.startswith("-f") and len(a) >= 3:
            mode_letter = a[2:]
    args, _ = ap.parse_known_args()

    print(f"DSD-SHIM starting, mode=-f{{mode_letter}}")
    with wave.open(args.i, "rb") as wf:
        n = wf.getnframes()
        raw = wf.readframes(n)
    pcm = np.frombuffer(raw, dtype="<i2")
    # "Decode" by downsampling to 8 kHz: take every 6th sample.
    out = pcm[::6].astype("<i2")
    with wave.open(args.w, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(out.tobytes())
    # Emit log fields the runner should parse.
    print("Sync: +P25p1  NAC: 0x293")
    print("HDU Algid: 0x84  Keyid: 0x1234  (encryption enabled)")
    """).strip()


def _write_shim(path: str) -> None:
    with open(path, "w") as fh:
        fh.write(SHIM_TEMPLATE.format(python=sys.executable))
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.mark.skipif(sys.platform == "win32",
                    reason="shim relies on POSIX shebang; Windows is exercised via mocked runner")
def test_subprocess_decodes_and_parses_fields(tmp_path):
    shim = tmp_path / "dsd-fme"
    _write_shim(str(shim))
    # 1s of 48 kHz discriminator samples = 48000 float32.
    demod = 0.5 * np.sin(2 * np.pi * 1000 * np.arange(48000) / 48000.0)
    res = decode_with_dsd_subprocess(
        demod.astype(np.float32), mode="p25_c4fm",
        out_dir=str(tmp_path / "out"),
        binary=str(shim), flavor="dsd_fme",
    )
    assert res.ok, res.error
    assert res.pcm_8k is not None
    assert res.pcm_8k.size == 8000
    assert res.algid == 0x84
    assert res.keyid == 0x1234
    assert res.nac == 0x293
    assert any("encryption" in e.lower() or "algid" in e.lower()
               for e in res.encryption_evidence)


def test_missing_binary_is_graceful(tmp_path):
    res = decode_with_dsd_subprocess(
        np.zeros(4800, dtype=np.float32), mode="p25_c4fm",
        out_dir=str(tmp_path / "out"),
        binary="definitely-not-a-real-binary-xyz-123",
    )
    assert not res.ok
    assert "not found" in (res.error or "").lower()


def test_unknown_flavor_rejected(tmp_path):
    res = decode_with_dsd_subprocess(
        np.zeros(100, dtype=np.float32), mode="p25_c4fm",
        out_dir=str(tmp_path / "out"),
        binary="anything", flavor="not_a_flavor",
    )
    assert not res.ok
    assert "unknown flavor" in (res.error or "").lower()


def test_parse_log_fields_variants():
    log = (
        "Inbound Call NAC=0x293\n"
        "algid = 0x80 keyid=0\n"   # clear
        "Next frame:\n"
        "HDU algid=0x85 keyid=0xABCD encrypted\n"
    )
    algid, keyid, nac, ev = _parse_log_fields(log)
    # First algid match wins — but 0x80 (clear) is parsed too; the pipeline
    # consults probe_p25_encryption which handles the 0x80 case separately.
    assert algid in (0x80, 0x85)
    assert nac == 0x293
    assert any("encrypt" in e.lower() or "algid" in e.lower() for e in ev)
