"""dsd-fme subprocess adapter.

Reads a channel SigMF file (cf32 baseband, FM family), runs the FM
discriminator, resamples to 48 kHz, writes a temporary WAV, and invokes
``dsd-fme`` with the correct ``-f<mode>`` flag. Parses algid / keyid / NAC
from dsd-fme's stdout into per-frame FrameRecords.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple

import numpy as np

from ..demod.fm_disc import fm_discriminator
from ..demod.wav_writer import read_wav_as_float, write_mono_int16_wav
from .base import DecodeOptions, DecodeResult, FrameRecord, ProtocolAdapter
from .registry import register_adapter


_MODE_TO_FLAG = {
    "p25_c4fm": "1",
    "dmr":      "s",
    "dpmr":     "m",
    "dstar":    "d",
    "nxdn48":   "i",
    "nxdn96":   "n",
    "provoice": "p",
    "x2_tdma":  "x",
    "auto":     "a",
}

_RE_NAC   = re.compile(r"(?i)\bNAC[^0-9a-fx]*(0x[0-9a-f]+|\d+)")
_RE_ALGID = re.compile(r"(?i)\balgid[^0-9a-fx]*(0x[0-9a-f]+|\d+)")
_RE_KEYID = re.compile(r"(?i)\bkeyid[^0-9a-fx]*(0x[0-9a-f]+|\d+)")
_RE_HDU   = re.compile(r"(?i)(HDU|Header Data Unit)")
_RE_LDU   = re.compile(r"(?i)\bLDU(1|2)?\b")
_RE_DMR_VOICE = re.compile(r"(?i)Voice (Frame|Burst)|VC(6|5|4|3|2|1)")
_RE_ENCRYPT_LINE = re.compile(
    r"(?i)(encrypted|encryption|ADP|ARC4|AES|DES-OFB|PI header|cipher)"
)
# Trunking-related fields surfaced by dsd-fme's stdout. These are protocol-
# agnostic — the trunking module disambiguates P25 vs DMR via context.
_RE_TG    = re.compile(r"(?i)\b(?:TG|TGID|talkgroup|target)[^0-9a-fx]*"
                       r"(0x[0-9a-f]+|\d+)")
_RE_SRC   = re.compile(r"(?i)\b(?:SRC|SUID|source|RID)[^0-9a-fx]*"
                       r"(0x[0-9a-f]+|\d+)")
_RE_LCN   = re.compile(r"(?i)\bLCN[^0-9a-fx]*(0x[0-9a-f]+|\d+)")
_RE_FREQ_MHZ = re.compile(r"(?i)\bfreq[^0-9.]*([0-9]+\.[0-9]+)\s*MHz")
_RE_GRANT = re.compile(r"(?i)(channel grant|voice channel|group voice|TSBK|"
                       r"CSBK|grant|update)")
_RE_PDU   = re.compile(r"(?i)\bPDU\s*(?:0x([0-9a-f]+)|(\d+))\b")


def _parse_hex_or_dec(tok: str) -> Optional[int]:
    try:
        return int(tok, 16) if tok.lower().startswith("0x") else int(tok)
    except ValueError:
        return None


def _parse_log(log: str, duration_s: float) -> Tuple[
        List[FrameRecord], Optional[int], Optional[int], Optional[int]]:
    """Turn the dsd-fme stdout into a list of FrameRecord + aggregate fields.

    The stdout is line-based. Each matching line becomes one frame; timestamps
    are distributed linearly across the channel's duration since dsd-fme does
    not emit per-frame timestamps in a stable format.
    """
    lines = log.splitlines()
    records: List[FrameRecord] = []
    first_nac = first_algid = first_keyid = None
    interesting: List[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        if (_RE_HDU.search(ln) or _RE_LDU.search(ln)
                or _RE_DMR_VOICE.search(ln)
                or _RE_NAC.search(ln) or _RE_ALGID.search(ln)
                or _RE_ENCRYPT_LINE.search(ln)
                or _RE_GRANT.search(ln) or _RE_TG.search(ln)
                or _RE_LCN.search(ln) or _RE_FREQ_MHZ.search(ln)):
            interesting.append((i, ln))
    if not interesting:
        return records, first_nac, first_algid, first_keyid

    # Distribute times evenly.
    for k, (i, ln) in enumerate(interesting):
        t = (k / max(len(interesting) - 1, 1)) * duration_s
        ftype = "unknown"
        if _RE_HDU.search(ln):
            ftype = "P25_HDU"
        elif m := _RE_LDU.search(ln):
            ftype = f"P25_LDU{m.group(1) or ''}".strip()
        elif _RE_DMR_VOICE.search(ln):
            ftype = "DMR_VOICE"
        elif _RE_GRANT.search(ln):
            ftype = "TRUNKING_GRANT"
        elif _RE_TG.search(ln) or _RE_LCN.search(ln):
            ftype = "TRUNKING_INFO"
        elif _RE_ENCRYPT_LINE.search(ln):
            ftype = "ENCRYPTION_EVIDENCE"
        extras = {"log_line": ln.strip()[:240]}
        if m := _RE_TG.search(ln):
            v = _parse_hex_or_dec(m.group(1))
            if v is not None:
                extras["talkgroup_id"] = v
        if m := _RE_SRC.search(ln):
            v = _parse_hex_or_dec(m.group(1))
            if v is not None:
                extras["source_id"] = v
        if m := _RE_LCN.search(ln):
            v = _parse_hex_or_dec(m.group(1))
            if v is not None:
                extras["lcn"] = v
        if m := _RE_FREQ_MHZ.search(ln):
            try:
                extras["grant_freq_hz"] = float(m.group(1)) * 1e6
            except ValueError:
                pass
        if m := _RE_PDU.search(ln):
            tok = m.group(1) or m.group(2)
            v = _parse_hex_or_dec(("0x" + tok) if m.group(1) else tok)
            if v is not None:
                extras["pdu"] = v
        if m := _RE_NAC.search(ln):
            v = _parse_hex_or_dec(m.group(1))
            if v is not None:
                extras["nac"] = v
                first_nac = first_nac if first_nac is not None else v
        if m := _RE_ALGID.search(ln):
            v = _parse_hex_or_dec(m.group(1))
            if v is not None:
                extras["algid"] = v
                first_algid = first_algid if first_algid is not None else v
        if m := _RE_KEYID.search(ln):
            v = _parse_hex_or_dec(m.group(1))
            if v is not None:
                extras["keyid"] = v
                first_keyid = first_keyid if first_keyid is not None else v
        records.append(FrameRecord(t_offset_s=t, type=ftype, extras=extras))
    return records, first_nac, first_algid, first_keyid


def _resample_to_48k(x: np.ndarray, src_rate_hz: float) -> np.ndarray:
    if abs(src_rate_hz - 48_000.0) < 1.0:
        return x.astype(np.float32, copy=False)
    from fractions import Fraction
    frac = Fraction(48_000).limit_denominator(10_000) / Fraction(int(round(src_rate_hz)))
    up = frac.numerator
    down = frac.denominator
    from scipy.signal import resample_poly
    return resample_poly(x, up, down).astype(np.float32)


@register_adapter
class DsdFmeAdapter(ProtocolAdapter):
    name = "dsd_fme"
    protocols = ("p25_c4fm", "dmr", "dpmr")
    demod_hint = "fm"

    def is_available(self) -> bool:
        # Honoured at runtime with the binary from DecodeOptions; the registry
        # check is coarse. We return True here so the orchestrator can try
        # us, and the error-path in decode() handles missing binary cleanly.
        return True

    def decode(self, channel_meta_path: str, opts: DecodeOptions
               ) -> DecodeResult:
        try:
            meta = self.load_channel_meta(channel_meta_path)
        except Exception as exc:
            return DecodeResult(
                event_id=os.path.splitext(os.path.basename(channel_meta_path))[0],
                protocol="unknown", adapter=self.name, ok=False,
                error=f"failed to read channel meta: {exc}",
            )
        g = meta["global"]
        event_id = g.get("wbdec:event_id") or os.path.splitext(
            os.path.basename(channel_meta_path))[0]
        label = g.get("wbdec:label") or "unknown"
        if label not in _MODE_TO_FLAG:
            return DecodeResult(
                event_id=event_id, protocol=label, adapter=self.name, ok=False,
                error=f"dsd-fme has no mode letter for label {label}",
            )
        bin_path = opts.dsd_fme_binary
        if shutil.which(bin_path) is None and not os.path.isabs(bin_path):
            return DecodeResult(
                event_id=event_id, protocol=label, adapter=self.name, ok=False,
                error=f"{bin_path} not found on PATH",
            )
        fs = float(g["core:sample_rate"])
        data_path = self.channel_data_path(channel_meta_path)
        if not os.path.exists(data_path):
            return DecodeResult(
                event_id=event_id, protocol=label, adapter=self.name, ok=False,
                error=f"channel data file missing: {data_path}",
            )

        raw = np.fromfile(data_path, dtype="<f4")
        iq = (raw[0::2] + 1j * raw[1::2]).astype(np.complex64)
        duration_s = iq.size / max(fs, 1.0)
        demod = fm_discriminator(iq, gain=1.6 / np.pi)
        demod_48k = _resample_to_48k(demod, fs)

        calls_dir = os.path.join(opts.out_dir, "calls")
        frames_dir = os.path.join(opts.out_dir, "frames")
        os.makedirs(calls_dir, exist_ok=True)
        os.makedirs(frames_dir, exist_ok=True)

        in_wav = os.path.join(calls_dir, f"_{event_id}_disc.wav")
        out_wav = os.path.join(calls_dir, f"{event_id}.wav")
        log_path = os.path.join(calls_dir, f"{event_id}.dsd.log")
        write_mono_int16_wav(in_wav, demod_48k, 48000)

        cmd = [bin_path, f"-f{_MODE_TO_FLAG[label]}", "-i", in_wav, "-w", out_wav]
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
                event_id=event_id, protocol=label, adapter=self.name, ok=False,
                error=f"{bin_path} timed out after {opts.timeout_s}s",
                duration_s=duration_s,
            )
        except Exception as exc:
            return DecodeResult(
                event_id=event_id, protocol=label, adapter=self.name, ok=False,
                error=f"failed to invoke {bin_path}: {exc}",
                duration_s=duration_s,
            )
        finally:
            try:
                os.unlink(in_wav)
            except OSError:
                pass

        with open(log_path, "r", errors="ignore") as fh:
            log = fh.read()
        frames, nac, algid, keyid = _parse_log(log, duration_s)

        frames_jsonl_path = os.path.join(frames_dir, f"{event_id}.jsonl")
        with open(frames_jsonl_path, "w") as fh:
            for fr in frames:
                fh.write(fr.to_json_line())
                fh.write("\n")

        pcm, out_sr = read_wav_as_float(out_wav)
        ok = pcm is not None and pcm.size > 0
        return DecodeResult(
            event_id=event_id, protocol=label, adapter=self.name, ok=ok,
            pcm_wav_path=out_wav if ok else None,
            frames_jsonl_path=frames_jsonl_path,
            nac=nac, algid=algid, keyid=keyid,
            duration_s=duration_s, n_frames=len(frames),
            error=None if ok else f"dsd-fme produced no audio (exit={proc.returncode})",
        )
