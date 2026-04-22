"""osmocom-tetra `tetra-rx` subprocess adapter (optional).

Consumes a TETRA channel extracted by stage 3 (cf32 at 72 kHz with RRC
matched filter applied). Writes the baseband as interleaved cs16 (the
format tetra-rx accepts via its ``-i`` option in most builds) and parses
MAC-ENCR / Security-Class evidence from the log into FrameRecords.

If ``tetra-rx`` is not installed, the adapter degrades to ``ok=False``
with a clear error rather than raising.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import List, Optional

import numpy as np

from .base import DecodeOptions, DecodeResult, FrameRecord, ProtocolAdapter
from .registry import register_adapter


_MAC_ENCR = re.compile(r"(?i)MAC-ENCR[^\n]*class\s*(\d+)")
_TEA      = re.compile(r"\bTEA[1-4]\b", re.IGNORECASE)
_CIPHERED = re.compile(r"(?i)(?:ciphered|encrypted)\s*[=:]\s*(1|true|yes)")


@register_adapter
class TetraRxAdapter(ProtocolAdapter):
    name = "tetra_rx"
    protocols = ("tetra",)
    demod_hint = "linear"

    def is_available(self) -> bool:
        return True  # checked per-call via binary path

    def decode(self, channel_meta_path: str, opts: DecodeOptions
               ) -> DecodeResult:
        event_id = os.path.splitext(os.path.basename(channel_meta_path))[0]
        try:
            meta = self.load_channel_meta(channel_meta_path)
        except Exception as exc:
            return DecodeResult(
                event_id=event_id, protocol="tetra", adapter=self.name,
                ok=False, error=f"meta read failed: {exc}",
            )
        g = meta["global"]
        fs = float(g["core:sample_rate"])
        data_path = self.channel_data_path(channel_meta_path)
        if not os.path.exists(data_path):
            return DecodeResult(
                event_id=event_id, protocol="tetra", adapter=self.name,
                ok=False, error=f"channel data missing: {data_path}",
            )
        if shutil.which(opts.tetra_rx_binary) is None and not os.path.isabs(opts.tetra_rx_binary):
            return DecodeResult(
                event_id=event_id, protocol="tetra", adapter=self.name,
                ok=False,
                error=f"{opts.tetra_rx_binary} not on PATH; install osmocom-tetra or disable TETRA",
            )

        calls_dir = os.path.join(opts.out_dir, "calls")
        frames_dir = os.path.join(opts.out_dir, "frames")
        os.makedirs(calls_dir, exist_ok=True)
        os.makedirs(frames_dir, exist_ok=True)

        raw = np.fromfile(data_path, dtype="<f4")
        iq = (raw[0::2] + 1j * raw[1::2]).astype(np.complex64)
        duration_s = iq.size / max(fs, 1.0)
        # Convert to interleaved cs16.
        cs16 = np.empty(iq.size * 2, dtype="<i2")
        cs16[0::2] = np.clip(iq.real * 32767.0, -32768, 32767).astype("<i2")
        cs16[1::2] = np.clip(iq.imag * 32767.0, -32768, 32767).astype("<i2")
        with tempfile.NamedTemporaryFile(suffix=".cs16", delete=False) as tf:
            cs16.tofile(tf)
            in_path = tf.name

        out_raw = os.path.join(calls_dir, f"{event_id}.tetra.raw")
        log_path = os.path.join(calls_dir, f"{event_id}.tetra.log")
        cmd = [opts.tetra_rx_binary, "-i", in_path, "-o", out_raw]
        if opts.extra_args:
            cmd.extend(opts.extra_args)

        try:
            with open(log_path, "w") as logf:
                proc = subprocess.run(
                    cmd, stdout=logf, stderr=subprocess.STDOUT,
                    timeout=opts.timeout_s, check=False,
                )
        except subprocess.TimeoutExpired:
            return DecodeResult(
                event_id=event_id, protocol="tetra", adapter=self.name,
                ok=False, duration_s=duration_s,
                error=f"tetra-rx timed out after {opts.timeout_s}s",
            )
        except Exception as exc:
            return DecodeResult(
                event_id=event_id, protocol="tetra", adapter=self.name,
                ok=False, duration_s=duration_s,
                error=f"failed to invoke tetra-rx: {exc}",
            )
        finally:
            try:
                os.unlink(in_path)
            except OSError:
                pass

        with open(log_path, "r", errors="ignore") as fh:
            log = fh.read()

        # Build a minimal frame stream from log evidence. Real TETRA MAC
        # decoding happens upstream in tetra-rx; we just mirror its findings.
        records: List[FrameRecord] = []
        for i, line in enumerate(log.splitlines()):
            extras = {"log_line": line.strip()[:240]}
            if m := _MAC_ENCR.search(line):
                records.append(FrameRecord(
                    t_offset_s=i * (duration_s / max(len(log.splitlines()), 1)),
                    type="TETRA_MAC_ENCR",
                    extras={**extras, "security_class": int(m.group(1))},
                ))
            elif _TEA.search(line) or _CIPHERED.search(line):
                records.append(FrameRecord(
                    t_offset_s=i * (duration_s / max(len(log.splitlines()), 1)),
                    type="ENCRYPTION_EVIDENCE", extras=extras,
                ))

        frames_jsonl_path = os.path.join(frames_dir, f"{event_id}.jsonl")
        with open(frames_jsonl_path, "w") as fh:
            for fr in records:
                fh.write(fr.to_json_line() + "\n")

        ok = os.path.exists(out_raw) and os.path.getsize(out_raw) > 0
        return DecodeResult(
            event_id=event_id, protocol="tetra", adapter=self.name, ok=ok,
            pcm_wav_path=out_raw if ok else None,
            frames_jsonl_path=frames_jsonl_path,
            duration_s=duration_s, n_frames=len(records),
            error=None if ok else f"tetra-rx produced no audio (exit={proc.returncode})",
        )
