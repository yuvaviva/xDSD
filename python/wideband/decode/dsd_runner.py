"""Run dsd.block_ff against a 48 kHz discriminator stream in a tiny GR top_block.

If GNU Radio / dsd are not importable (e.g. during unit tests without the
compiled block), decode gracefully degrades and returns metadata-only output so
the pipeline stays functional.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np


@dataclass
class DsdDecodeResult:
    ok: bool
    pcm_8k: Optional[np.ndarray]
    mode: str
    algid: Optional[int] = None
    keyid: Optional[int] = None
    nac: Optional[int] = None
    error: Optional[str] = None


_MODE_TO_ENUM = {
    "p25_c4fm": "dsd_FRAME_P25_PHASE_1",
    "dmr": "dsd_FRAME_DMR_MOTOTRBO",
    "dstar": "dsd_FRAME_DSTAR",
    "nxdn48": "dsd_FRAME_NXDN48_IDAS",
    "nxdn96": "dsd_FRAME_NXDN96",
    "provoice": "dsd_FRAME_PROVOICE",
    "x2_tdma": "dsd_FRAME_X2_TDMA",
    "auto": "dsd_FRAME_AUTO_DETECT",
}

_MODE_TO_MOD = {
    "p25_c4fm": "dsd_MOD_C4FM",
    "dmr": "dsd_MOD_QPSK",
    "dstar": "dsd_MOD_GFSK",
    "nxdn48": "dsd_MOD_GFSK",
    "nxdn96": "dsd_MOD_GFSK",
    "provoice": "dsd_MOD_GFSK",
    "x2_tdma": "dsd_MOD_QPSK",
    "auto": "dsd_MOD_AUTO_SELECT",
}


def decode_with_dsd(discriminator_48k: np.ndarray, mode: str) -> DsdDecodeResult:
    """Drive dsd.block_ff with a pre-computed 48 kHz discriminator stream.

    Input must be float32, sample rate 48000, amplitude roughly ±1.
    Output PCM is 8 kHz int16 (from DSD) returned as int16 numpy array.
    """
    try:
        import dsd  # type: ignore
        from gnuradio import gr, blocks  # type: ignore
    except Exception as exc:
        return DsdDecodeResult(
            ok=False, pcm_8k=None, mode=mode, error=f"GNU Radio / dsd unavailable: {exc}",
        )
    if mode not in _MODE_TO_ENUM:
        return DsdDecodeResult(ok=False, pcm_8k=None, mode=mode,
                               error=f"Unknown mode: {mode}")
    frame_enum = getattr(dsd, _MODE_TO_ENUM[mode])
    mod_enum = getattr(dsd, _MODE_TO_MOD[mode])

    samples = np.asarray(discriminator_48k, dtype=np.float32)
    tb = gr.top_block()
    src = blocks.vector_source_f(samples.tolist(), False)
    dsd_blk = dsd.block_ff(frame_enum, mod_enum, 3, True, 0, False, -1)
    sink = blocks.vector_sink_s()  # DSD emits int16
    tb.connect(src, dsd_blk, sink)
    tb.run()

    pcm = np.asarray(sink.data(), dtype=np.int16)
    algid = keyid = nac = None
    try:
        st = dsd_blk.get_state()
        # SWIG exposes dsd_state fields; best-effort extraction.
        algid = _safe_get(st, "algid")
        keyid = _safe_get(st, "keyid")
        nac = _safe_get(st, "nac")
    except Exception:
        pass
    return DsdDecodeResult(ok=True, pcm_8k=pcm, mode=mode,
                           algid=algid, keyid=keyid, nac=nac)


def _safe_get(obj, name):
    try:
        v = getattr(obj, name)
        # algid/keyid are char arrays; try to coerce into int if possible.
        if isinstance(v, (bytes, bytearray)):
            return int(v, 16) if v else None
        if isinstance(v, str):
            try:
                return int(v, 16)
            except ValueError:
                return v
        if isinstance(v, (list, tuple)) and v:
            return v[0]
        return v
    except Exception:
        return None
