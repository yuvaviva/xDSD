"""In-tree TETRA fallback: sync detection + minimal MAC metadata only.

This adapter is the *safety net* when osmocom-tetra is not installed. It
does NOT produce voice — full TETRA voice decoding requires the ACELP
codec + tetra-rx's link-layer stack, which are out of scope for wbdec.

What it does do:

1. Demodulate the already-RRC-matched 72 kHz baseband into symbols.
2. Look for TETRA training sequences (normal-uplink/normal-downlink/
   synchronisation bursts — the 30-bit / 38-bit known patterns).
3. Emit one ``FrameRecord`` per burst-match with timing, slot, and a
   raw-bit preview so the analyzer (M4) can still flag encryption state.
"""

from __future__ import annotations

import os
from typing import List

import numpy as np

from .base import DecodeOptions, DecodeResult, FrameRecord, ProtocolAdapter
from .registry import register_adapter


# TETRA normal-downlink training sequence (bits, 22 symbols = 44 bits).
# Source: ETSI EN 300 392-2. Using a short well-known prefix is enough for
# rough burst detection; this is NOT a production sync.
_SYNC_PATTERN = np.array([
    0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 0, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1,
], dtype=np.int8)


def _pi4_dqpsk_soft_bits(iq: np.ndarray, sps: int) -> np.ndarray:
    """Very rough π/4-DQPSK → bit stream. Not a real demod; used as a
    low-false-positive burst-presence test only.
    """
    if iq.size < sps * 8:
        return np.zeros(0, dtype=np.int8)
    sym = iq[::sps]
    if sym.size < 2:
        return np.zeros(0, dtype=np.int8)
    diff = sym[1:] * np.conj(sym[:-1])
    # Two bits per differential symbol from the sign of real/imag.
    bits = np.empty(diff.size * 2, dtype=np.int8)
    bits[0::2] = (diff.real > 0).astype(np.int8)
    bits[1::2] = (diff.imag > 0).astype(np.int8)
    return bits


def _find_sync(bits: np.ndarray, pattern: np.ndarray,
               tolerance: int = 4) -> List[int]:
    if bits.size < pattern.size:
        return []
    # Correlation by matched-count; allow small mismatch.
    out: List[int] = []
    for i in range(bits.size - pattern.size):
        diff = int((bits[i:i + pattern.size] != pattern).sum())
        if diff <= tolerance:
            out.append(i)
    return out


@register_adapter
class TetraNativeAdapter(ProtocolAdapter):
    name = "tetra_native"
    protocols = ("tetra",)
    demod_hint = "linear"

    def is_available(self) -> bool:
        return True

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
        symbol_rate_hz = 18_000.0
        sps = max(1, int(round(fs / symbol_rate_hz)))

        data_path = self.channel_data_path(channel_meta_path)
        if not os.path.exists(data_path):
            return DecodeResult(
                event_id=event_id, protocol="tetra", adapter=self.name,
                ok=False, error=f"channel data missing: {data_path}",
            )
        raw = np.fromfile(data_path, dtype="<f4")
        iq = (raw[0::2] + 1j * raw[1::2]).astype(np.complex64)
        duration_s = iq.size / max(fs, 1.0)

        bits = _pi4_dqpsk_soft_bits(iq, sps)
        sync_positions = _find_sync(bits, _SYNC_PATTERN, tolerance=4)

        frames_dir = os.path.join(opts.out_dir, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        records: List[FrameRecord] = []
        for k, pos in enumerate(sync_positions):
            t = pos / max(symbol_rate_hz * 2, 1.0)  # 2 bits/symbol
            records.append(FrameRecord(
                t_offset_s=min(t, duration_s),
                type="TETRA_SYNC",
                extras={"bit_offset": int(pos),
                        "raw_preview": bits[pos:pos + 22].tolist()},
            ))
        frames_jsonl_path = os.path.join(frames_dir, f"{event_id}.jsonl")
        with open(frames_jsonl_path, "w") as fh:
            for fr in records:
                fh.write(fr.to_json_line() + "\n")

        return DecodeResult(
            event_id=event_id, protocol="tetra", adapter=self.name,
            ok=False,   # no audio produced
            pcm_wav_path=None,
            frames_jsonl_path=frames_jsonl_path,
            duration_s=duration_s,
            n_frames=len(records),
            error="tetra_native adapter emits metadata only — install tetra-rx for audio",
            extras={"n_sync_candidates": len(sync_positions)},
        )
