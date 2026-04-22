"""Per-event streaming ChannelExtractor.

One instance per detected event. Given sequential chunks of the source
capture (with their absolute sample offsets in the full stream), it:

1. Applies a phase-continuous frequency shift (NCO that remembers its
   sample index across chunks).
2. Low-pass-filters with a FIR, preserving state via ``lfilter`` zi.
3. Decimates by the chosen integer factor.
4. Optionally applies the RRC matched filter at the decimated rate.
5. Emits the processed complex64 samples through a callback.

Time-bounded: samples outside ``[t_start, t_end]`` are skipped so the
output file contains only the active portion of the event.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from .grid import ChannelTarget
from .rrc import rrc_taps


def _design_lpf(cutoff_hz: float, sample_rate_hz: float,
                num_taps: int = 257) -> np.ndarray:
    """Windowed-sinc low-pass prototype with ~20% transition band."""
    from scipy.signal import firwin
    nyq = sample_rate_hz / 2.0
    transition = max(cutoff_hz * 0.2, 500.0)
    cutoff = min(cutoff_hz + transition / 2.0, nyq * 0.95)
    return firwin(num_taps, cutoff=cutoff / nyq, window="hamming").astype(np.float32)


@dataclass
class ExtractorConfig:
    event_id: str
    center_offset_hz: float       # relative to source center
    source_rate_hz: float
    target: ChannelTarget
    t_start_s: float
    t_end_s: float


class ChannelExtractor:
    """Streaming per-event channel extractor."""

    def __init__(self, cfg: ExtractorConfig,
                 on_samples: Callable[[np.ndarray], None]):
        self.cfg = cfg
        self._on_samples = on_samples

        self.lpf_taps = _design_lpf(cfg.target.channel_bw_hz,
                                    cfg.source_rate_hz, num_taps=257)
        # Decimation chosen against a slightly padded target so the LPF
        # cutoff stays well within Nyquist after decimation.
        dec = int(cfg.source_rate_hz // cfg.target.out_rate_hz)
        dec = max(dec, 1)
        # Tighten: require LPF cutoff ≤ fs_post_decim / 2.
        while cfg.target.channel_bw_hz > (cfg.source_rate_hz / dec) * 0.45 and dec > 1:
            dec -= 1
        self.decimation = dec
        self.out_rate_hz = cfg.source_rate_hz / dec

        # Frequency-shift phase state.
        self._phase = 0.0
        self._phase_inc = -2.0 * np.pi * cfg.center_offset_hz / cfg.source_rate_hz

        # LPF state (zi). Initialised to zero; size is num_taps - 1.
        self._lpf_zi = np.zeros(len(self.lpf_taps) - 1, dtype=np.complex64)

        # Decimation phase — preserve remainder across chunks.
        self._dec_phase = 0

        # Optional RRC matched filter at output rate.
        self._rrc_taps: Optional[np.ndarray] = None
        self._rrc_zi: Optional[np.ndarray] = None
        if cfg.target.apply_rrc:
            self._rrc_taps = rrc_taps(
                sample_rate_hz=self.out_rate_hz,
                symbol_rate_hz=cfg.target.rrc_symbol_rate_hz,
                rolloff=cfg.target.rrc_rolloff,
                num_symbols=8,
            )
            self._rrc_zi = np.zeros(len(self._rrc_taps) - 1,
                                    dtype=np.complex64)

        # Output sample accumulator for reporting.
        self.samples_written = 0

    def is_active_for_chunk(self, chunk_start_t_s: float,
                            chunk_end_t_s: float) -> bool:
        return (chunk_end_t_s >= self.cfg.t_start_s
                and chunk_start_t_s <= self.cfg.t_end_s)

    def push_chunk(self, chunk: np.ndarray, chunk_start_t_s: float) -> None:
        from scipy.signal import lfilter
        n = chunk.size
        if n == 0:
            return

        # Time-clip the chunk to [t_start, t_end] of this event.
        fs = self.cfg.source_rate_hz
        chunk_end_t_s = chunk_start_t_s + n / fs
        lo_t = max(chunk_start_t_s, self.cfg.t_start_s)
        hi_t = min(chunk_end_t_s, self.cfg.t_end_s)
        if hi_t <= lo_t:
            return
        lo_n = int(round((lo_t - chunk_start_t_s) * fs))
        hi_n = int(round((hi_t - chunk_start_t_s) * fs))
        clip = chunk[lo_n:hi_n]
        if clip.size == 0:
            return

        # 1. NCO mix down.
        ph = self._phase + self._phase_inc * np.arange(clip.size)
        shifted = (clip * np.exp(1j * ph)).astype(np.complex64)
        self._phase = float((self._phase + self._phase_inc * clip.size)
                            % (2.0 * np.pi))

        # 2. LPF (state-preserving).
        filtered, self._lpf_zi = lfilter(
            self.lpf_taps.astype(np.complex64),
            np.array([1.0 + 0j], dtype=np.complex64),
            shifted, zi=self._lpf_zi,
        )
        filtered = filtered.astype(np.complex64)

        # 3. Decimate with per-chunk phase carry-over.
        # self._dec_phase is the sample index (within THIS chunk's filtered
        # output) of the next sample we want to keep. Always < decimation
        # across chunks.
        dp = self._dec_phase
        L = filtered.size
        dec = self.decimation
        if dp >= L:
            decimated = filtered[0:0]
            self._dec_phase = dp - L
        else:
            # indices kept: dp, dp+dec, dp+2*dec, ... while < L
            decimated = filtered[dp::dec]
            kept = decimated.size
            last_kept = dp + (kept - 1) * dec
            next_abs = last_kept + dec
            self._dec_phase = next_abs - L

        out = decimated
        # 4. Optional RRC.
        if self._rrc_taps is not None:
            from scipy.signal import lfilter as _lf
            out, self._rrc_zi = _lf(
                self._rrc_taps.astype(np.complex64),
                np.array([1.0 + 0j], dtype=np.complex64),
                out, zi=self._rrc_zi,
            )
            out = out.astype(np.complex64)

        if out.size:
            self._on_samples(out)
            self.samples_written += out.size
