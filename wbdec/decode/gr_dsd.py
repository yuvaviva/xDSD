"""gr-dsd in-process adapter (optional, guarded behind try-import).

Registered for completeness. Selected by the orchestrator only when the
user sets ``use_gr_dsd=True`` in the config AND the ``dsd`` GNU Radio
extension module is importable. On Windows + radioconda this will nearly
always be unavailable; the adapter degrades to ``ok=False`` with a clear
error rather than raising.
"""

from __future__ import annotations

import os
from typing import Optional

import numpy as np

from ..demod.fm_disc import fm_discriminator
from .base import DecodeOptions, DecodeResult, ProtocolAdapter
from .registry import register_adapter


_MODE_TO_ENUM = {
    "p25_c4fm": "dsd_FRAME_P25_PHASE_1",
    "dmr":      "dsd_FRAME_DMR_MOTOTRBO",
}
_MODE_TO_MOD = {
    "p25_c4fm": "dsd_MOD_C4FM",
    "dmr":      "dsd_MOD_QPSK",
}


@register_adapter
class GrDsdAdapter(ProtocolAdapter):
    name = "gr_dsd"
    protocols = ("p25_c4fm", "dmr")
    demod_hint = "fm"

    def is_available(self) -> bool:
        try:
            import dsd  # type: ignore
            return all(hasattr(dsd, a) for a in (
                "dsd_FRAME_P25_PHASE_1", "dsd_FRAME_DMR_MOTOTRBO", "block_ff"))
        except Exception:
            return False

    def decode(self, channel_meta_path: str, opts: DecodeOptions
               ) -> DecodeResult:
        event_id = os.path.splitext(os.path.basename(channel_meta_path))[0]
        try:
            import dsd  # type: ignore
            from gnuradio import gr, blocks  # type: ignore
        except Exception as exc:
            return DecodeResult(
                event_id=event_id, protocol="unknown", adapter=self.name, ok=False,
                error=f"gr-dsd unavailable: {exc}",
            )
        try:
            meta = self.load_channel_meta(channel_meta_path)
        except Exception as exc:
            return DecodeResult(
                event_id=event_id, protocol="unknown", adapter=self.name, ok=False,
                error=f"meta read failed: {exc}",
            )
        g = meta["global"]
        label = g.get("wbdec:label") or "unknown"
        if label not in _MODE_TO_ENUM:
            return DecodeResult(
                event_id=event_id, protocol=label, adapter=self.name, ok=False,
                error=f"gr-dsd mapping missing for label {label}",
            )
        fs = float(g["core:sample_rate"])
        data_path = self.channel_data_path(channel_meta_path)
        raw = np.fromfile(data_path, dtype="<f4")
        iq = (raw[0::2] + 1j * raw[1::2]).astype(np.complex64)
        demod = fm_discriminator(iq, gain=1.6 / np.pi)

        # Resample to 48 kHz via scipy.
        from ..decode.dsd_fme import _resample_to_48k
        demod_48k = _resample_to_48k(demod, fs)

        tb = gr.top_block()
        src = blocks.vector_source_f(demod_48k.tolist(), False)
        blk = dsd.block_ff(
            getattr(dsd, _MODE_TO_ENUM[label]),
            getattr(dsd, _MODE_TO_MOD[label]),
            3, True, 0, False, -1,
        )
        sink = blocks.vector_sink_s()
        tb.connect(src, blk, sink)
        tb.run()
        pcm = np.asarray(sink.data(), dtype=np.int16)

        calls_dir = os.path.join(opts.out_dir, "calls")
        os.makedirs(calls_dir, exist_ok=True)
        wav_path = os.path.join(calls_dir, f"{event_id}.wav")
        from ..demod.wav_writer import write_mono_int16_wav
        write_mono_int16_wav(wav_path, pcm.astype(np.float32) / 32768.0, 8000)

        algid = keyid = nac = None
        try:
            st = blk.get_state()
            for name in ("algid", "keyid", "nac"):
                v = getattr(st, name, None)
                if v is not None and hasattr(v, "__getitem__"):
                    try:
                        locals()[name] = int(v[0])  # type: ignore[misc]
                    except Exception:
                        pass
        except Exception:
            pass

        return DecodeResult(
            event_id=event_id, protocol=label, adapter=self.name,
            ok=pcm.size > 0,
            pcm_wav_path=wav_path if pcm.size > 0 else None,
            duration_s=len(iq) / max(fs, 1.0),
            n_frames=0,
            nac=nac, algid=algid, keyid=keyid,
        )
