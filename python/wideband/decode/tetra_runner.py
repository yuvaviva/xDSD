"""TETRA decoding via the external osmocom-tetra `tetra-rx` binary."""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np


_ENCR_RE = re.compile(r"(?i)(MAC-ENCR|Security Class|SCK|Encryption)[^\n]*")


@dataclass
class TetraDecodeResult:
    ok: bool
    pcm_path: Optional[str] = None
    raw_log: str = ""
    encryption_evidence: List[str] = field(default_factory=list)
    error: Optional[str] = None


def decode_with_tetra_rx(iq_baseband: np.ndarray, sample_rate: float,
                         out_dir: str, tetra_rx_bin: str = "tetra-rx"
                         ) -> TetraDecodeResult:
    """Feed complex baseband to `tetra-rx` via a temp file and collect output.

    tetra-rx from osmocom-tetra expects float symbol samples at 36 ksps after
    demodulation. Here we write raw cs16 baseband to a pipe and invoke the
    full osmocom pipeline if available; otherwise we degrade gracefully.
    """
    if shutil.which(tetra_rx_bin) is None:
        return TetraDecodeResult(
            ok=False,
            error=f"{tetra_rx_bin} not found on PATH; install osmocom-tetra or disable TETRA.",
        )
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".cs16", delete=False) as tmp:
        # cs16 = interleaved int16 I/Q.
        iq_scaled = (iq_baseband * 32767.0).astype("<i2")
        pkt = np.empty(iq_scaled.size * 2, dtype="<i2")
        pkt[0::2] = iq_scaled.real.astype("<i2") if np.iscomplexobj(iq_baseband) else iq_scaled
        pkt[1::2] = iq_scaled.imag.astype("<i2") if np.iscomplexobj(iq_baseband) else 0
        pkt.tofile(tmp)
        tmp_path = tmp.name
    log_path = os.path.join(out_dir, "tetra_rx.log")
    pcm_path = os.path.join(out_dir, "tetra_voice.raw")
    try:
        with open(log_path, "w") as logf, open(pcm_path, "wb") as pcmf:
            proc = subprocess.Popen(
                [tetra_rx_bin, "-i", tmp_path, "-o", pcm_path],
                stdout=logf, stderr=subprocess.STDOUT, text=True,
            )
            proc.communicate(timeout=60.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        return TetraDecodeResult(ok=False, error="tetra-rx timed out")
    except Exception as exc:
        return TetraDecodeResult(ok=False, error=f"tetra-rx invocation failed: {exc}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    with open(log_path, "r", errors="ignore") as fh:
        log = fh.read()
    evidence = _ENCR_RE.findall(log)
    return TetraDecodeResult(
        ok=os.path.getsize(pcm_path) > 0,
        pcm_path=pcm_path if os.path.getsize(pcm_path) > 0 else None,
        raw_log=log,
        encryption_evidence=evidence,
    )
