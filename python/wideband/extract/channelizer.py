"""Single-channel extraction by frequency translate + LPF + decimate."""

from __future__ import annotations

from typing import Tuple

import numpy as np


def design_lpf(cutoff_hz: float, sample_rate: float, num_taps: int = 129,
               transition_hz: float = None) -> np.ndarray:
    """Windowed-sinc real-coefficient LPF centered on DC."""
    from scipy.signal import firwin
    transition = transition_hz or max(cutoff_hz * 0.25, 500.0)
    nyq = sample_rate / 2.0
    cutoff = min(cutoff_hz + transition / 2.0, nyq * 0.95)
    return firwin(num_taps, cutoff=cutoff / nyq, window="hamming").astype(np.float32)


def extract_channel(iq: np.ndarray, sample_rate: float,
                    center_offset_hz: float, channel_bw_hz: float,
                    out_sample_rate: float
                    ) -> Tuple[np.ndarray, float]:
    """Shift channel to DC, LPF, decimate (integer), resample to out_sample_rate.

    Returns (baseband_complex64, actual_out_rate).
    """
    from scipy.signal import resample_poly, fftconvolve
    n = iq.size
    t = np.arange(n, dtype=np.float32)
    shifted = iq * np.exp(-2j * np.pi * center_offset_hz * t / sample_rate)
    taps = design_lpf(channel_bw_hz / 2.0, sample_rate, num_taps=257)
    filtered = fftconvolve(shifted, taps.astype(np.complex64), mode="same")
    # Integer decimation to stay above Nyquist of channel bw.
    target_rate = max(out_sample_rate, channel_bw_hz * 2.5)
    dec = max(1, int(sample_rate // target_rate))
    decimated = filtered[::dec]
    inter_rate = sample_rate / dec
    # Final rational resample to requested out_sample_rate.
    if abs(inter_rate - out_sample_rate) > 1.0:
        # Use a modest up/down ratio for resample_poly stability.
        up = int(round(out_sample_rate))
        down = int(round(inter_rate))
        g = _gcd(up, down)
        up, down = up // g, down // g
        resampled = resample_poly(decimated, up, down).astype(np.complex64)
    else:
        resampled = decimated.astype(np.complex64)
    return resampled, inter_rate * len(resampled) / max(len(decimated), 1)


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a
