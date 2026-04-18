"""Subprocess-based DSD runner for Windows and non-GR environments.

Drives a standalone command-line decoder (DSD+, DSDcc, dsd-fme, or the
upstream szechyjs/dsd) instead of the gr-dsd GNU Radio block. This lets the
wideband pipeline produce decoded voice WAVs on machines where the gr-dsd
C++ block cannot be built (notably Windows + radioconda with GNU Radio 3.10).

Supported ``flavor`` values:

- ``dsd_fme`` / ``dsd`` / ``dsdcc`` — classic szechyjs-style CLI with
  ``-i <input.wav>`` ``-w <output.wav>`` ``-f<mode>`` flags. The 48 kHz
  discriminator samples are written as a mono 16-bit WAV and consumed
  directly.
- ``dsdplus`` — Van Valkenburg DSD+ Windows build. Accepts similar flags but
  the mode letter mapping differs for a few families.

The runner is intentionally tolerant: missing binary, timeout, or non-zero
exit all produce a structured ``DsdSubprocessResult`` rather than raising.
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass
class DsdSubprocessResult:
    ok: bool
    pcm_8k: Optional[np.ndarray]
    mode: str
    flavor: str
    algid: Optional[int] = None
    keyid: Optional[int] = None
    nac: Optional[int] = None
    log: str = ""
    encryption_evidence: List[str] = field(default_factory=list)
    error: Optional[str] = None
    wav_path: Optional[str] = None


# Mode letter mappings per flavor. The value is the string appended after ``-f``.
# Flag letters verified against the `dsd-fme -h` output ("dsd_fme" flavor) and
# upstream szechyjs/dsd docs ("dsd" flavor). dsd-fme replaces szechyjs's `-fr`
# (DMR) with `-fs` (DMR simplex) and adds `-fm` for dPMR.
_MODE_TO_FLAG: Dict[str, Dict[str, str]] = {
    "dsd_fme": {
        "p25_c4fm": "1",
        "dmr":      "s",
        "dstar":    "d",
        "nxdn48":   "i",
        "nxdn96":   "n",
        "provoice": "p",
        "x2_tdma":  "x",
        "dpmr":     "m",
        "auto":     "a",
    },
    "dsd": {
        "p25_c4fm": "1",
        "dmr":      "r",
        "dstar":    "d",
        "nxdn48":   "i",
        "nxdn96":   "n",
        "provoice": "p",
        "x2_tdma":  "x",
        "auto":     "a",
    },
    "dsdcc": {
        "p25_c4fm": "1",
        "dmr":      "r",
        "dstar":    "d",
        "nxdn48":   "i",
        "nxdn96":   "n",
        "provoice": "p",
        "auto":     "a",
    },
    "dsdplus": {
        "p25_c4fm": "1",
        "dmr":      "r",
        "dstar":    "d",
        "nxdn48":   "i",
        "nxdn96":   "n",
        "provoice": "p",
        "auto":     "a",
    },
}


_ALGID_RE = re.compile(r"(?i)algid[^0-9a-fx]*(0x[0-9a-f]+|\d+)")
_KEYID_RE = re.compile(r"(?i)keyid[^0-9a-fx]*(0x[0-9a-f]+|\d+)")
_NAC_RE = re.compile(r"(?i)\bNAC[^0-9a-fx]*(0x[0-9a-f]+|\d+)")
_ENC_RE = re.compile(
    r"(?i)(encrypted|encryption|algid\s*=\s*0x(?!80)[0-9a-f]+|"
    r"ADP|ARC4|AES|DES-OFB|PI header|encryption enabled)"
)


def _write_discriminator_wav(path: str, samples: np.ndarray,
                             sample_rate: int = 48000) -> None:
    s = np.asarray(samples, dtype=np.float32)
    # DSD expects -1..+1 range; clip gently and convert to int16 PCM mono.
    s = np.clip(s, -1.0, 1.0)
    pcm = (s * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm.tobytes())


def _read_output_wav(path: str) -> Optional[np.ndarray]:
    if not os.path.exists(path) or os.path.getsize(path) < 44:
        return None
    try:
        with wave.open(path, "rb") as wf:
            n = wf.getnframes()
            raw = wf.readframes(n)
            if wf.getsampwidth() != 2:
                return None
            return np.frombuffer(raw, dtype="<i2")
    except (wave.Error, EOFError):
        return None


def _parse_int(m: Optional[re.Match]) -> Optional[int]:
    if m is None:
        return None
    tok = m.group(1)
    try:
        return int(tok, 16) if tok.lower().startswith("0x") else int(tok)
    except ValueError:
        return None


def _parse_log_fields(log: str) -> Tuple[Optional[int], Optional[int],
                                         Optional[int], List[str]]:
    algid = _parse_int(_ALGID_RE.search(log))
    keyid = _parse_int(_KEYID_RE.search(log))
    nac = _parse_int(_NAC_RE.search(log))
    evidence = list({m.group(0).strip() for m in _ENC_RE.finditer(log)})
    return algid, keyid, nac, evidence


def decode_with_dsd_subprocess(
    discriminator_48k: np.ndarray,
    mode: str,
    out_dir: str,
    binary: str = "dsd-fme",
    flavor: str = "dsd_fme",
    extra_args: Optional[List[str]] = None,
    timeout_s: float = 60.0,
) -> DsdSubprocessResult:
    """Run a DSD-family CLI against a 48 kHz discriminator stream.

    ``binary`` is the executable to invoke (on PATH or absolute path).
    ``flavor`` selects the argument mapping. ``extra_args`` are appended
    verbatim — use this for ``["-U"]`` to force unmute-encrypted, etc.
    """
    flavor = flavor.lower()
    if flavor not in _MODE_TO_FLAG:
        return DsdSubprocessResult(
            ok=False, pcm_8k=None, mode=mode, flavor=flavor,
            error=f"unknown flavor: {flavor}",
        )
    if mode not in _MODE_TO_FLAG[flavor]:
        return DsdSubprocessResult(
            ok=False, pcm_8k=None, mode=mode, flavor=flavor,
            error=f"flavor {flavor} has no mapping for mode {mode}",
        )
    if shutil.which(binary) is None and not os.path.isabs(binary):
        return DsdSubprocessResult(
            ok=False, pcm_8k=None, mode=mode, flavor=flavor,
            error=f"binary not found on PATH: {binary}",
        )
    os.makedirs(out_dir, exist_ok=True)

    in_wav = os.path.join(out_dir, "_dsd_in.wav")
    out_wav = os.path.join(out_dir, "voice_8k.wav")
    log_path = os.path.join(out_dir, "dsd.log")
    _write_discriminator_wav(in_wav, discriminator_48k, sample_rate=48000)

    mode_flag = f"-f{_MODE_TO_FLAG[flavor][mode]}"
    cmd = [binary, mode_flag, "-i", in_wav, "-w", out_wav]
    if extra_args:
        cmd.extend(extra_args)

    log = ""
    try:
        with open(log_path, "w") as logf:
            proc = subprocess.run(
                cmd, stdout=logf, stderr=subprocess.STDOUT,
                timeout=timeout_s, check=False,
            )
        with open(log_path, "r", errors="ignore") as fh:
            log = fh.read()
    except FileNotFoundError as exc:
        return DsdSubprocessResult(
            ok=False, pcm_8k=None, mode=mode, flavor=flavor,
            error=f"failed to spawn {binary}: {exc}",
        )
    except subprocess.TimeoutExpired:
        return DsdSubprocessResult(
            ok=False, pcm_8k=None, mode=mode, flavor=flavor, log=log,
            error=f"{binary} timed out after {timeout_s}s",
        )
    finally:
        try:
            os.unlink(in_wav)
        except OSError:
            pass

    pcm = _read_output_wav(out_wav)
    algid, keyid, nac, evidence = _parse_log_fields(log)
    ok = pcm is not None and pcm.size > 0
    err = None if ok else f"{binary} produced no audio (exit={proc.returncode})"
    return DsdSubprocessResult(
        ok=ok, pcm_8k=pcm, mode=mode, flavor=flavor,
        algid=algid, keyid=keyid, nac=nac,
        log=log, encryption_evidence=evidence,
        error=err, wav_path=out_wav if ok else None,
    )
