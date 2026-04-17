"""Signal features used by the rule-based classifier."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np


@dataclass
class ClassifyFeatures:
    occupied_bw_hz: float
    symbol_rate_est_hz: float
    level_count: int         # 2 or 4 (dominant peaks in demod histogram)
    peak_deviation_hz: float
    const_phase_variance: float  # for π/4-DQPSK vs FM discrimination
    envelope_variance: float     # near-constant-envelope (FM) vs varying (PSK)


def estimate_occupied_bandwidth(iq: np.ndarray, sample_rate: float,
                                energy_fraction: float = 0.99) -> float:
    """99% occupied-bandwidth estimate via cumulative PSD integration."""
    n = min(len(iq), 1 << 15)
    x = iq[:n] * np.hanning(n)
    sp = np.fft.fftshift(np.fft.fft(x))
    psd = (sp.real ** 2 + sp.imag ** 2)
    total = psd.sum()
    if total <= 0:
        return 0.0
    cum = np.cumsum(psd)
    lo_t = (1.0 - energy_fraction) / 2.0 * total
    hi_t = (1.0 + energy_fraction) / 2.0 * total
    lo_bin = int(np.searchsorted(cum, lo_t))
    hi_bin = int(np.searchsorted(cum, hi_t))
    return float((hi_bin - lo_bin) * sample_rate / n)


def estimate_symbol_rate(iq: np.ndarray, sample_rate: float,
                         f_min: float = 1200.0, f_max: float = 24000.0
                         ) -> float:
    """Cyclostationary symbol-rate estimate via |x|^2 spectrum peak."""
    n = min(len(iq), 1 << 16)
    if n < 1024:
        return 0.0
    x2 = np.abs(iq[:n]) ** 2
    x2 = x2 - x2.mean()
    sp = np.fft.rfft(x2 * np.hanning(n))
    freqs = np.fft.rfftfreq(n, 1.0 / sample_rate)
    mask = (freqs >= f_min) & (freqs <= f_max)
    if not mask.any():
        return 0.0
    peak = int(np.argmax(np.abs(sp[mask])))
    return float(freqs[mask][peak])


def level_histogram(demod: np.ndarray, n_bins: int = 64
                    ) -> Tuple[int, np.ndarray]:
    """Count dominant peaks in the demod-sample histogram (2 for 2FSK, 4 for 4FSK)."""
    if demod.size == 0:
        return 0, np.zeros(n_bins)
    lo, hi = np.percentile(demod, [1, 99])
    if hi <= lo:
        return 0, np.zeros(n_bins)
    h, _ = np.histogram(demod, bins=n_bins, range=(lo, hi))
    # Smooth then count local maxima above a relative floor.
    k = np.ones(3) / 3.0
    hs = np.convolve(h, k, mode="same")
    thr = hs.max() * 0.25
    peaks = 0
    for i in range(1, len(hs) - 1):
        if hs[i] > thr and hs[i] >= hs[i - 1] and hs[i] >= hs[i + 1]:
            peaks += 1
    return peaks, hs


def peak_deviation(demod: np.ndarray, sample_rate: float) -> float:
    """Rough peak frequency deviation, assuming `demod` is instantaneous freq in rad/sample."""
    if demod.size == 0:
        return 0.0
    dev_rad = float(np.percentile(np.abs(demod), 95))
    return dev_rad * sample_rate / (2.0 * np.pi)


def envelope_variance(iq: np.ndarray) -> float:
    if iq.size == 0:
        return 0.0
    env = np.abs(iq)
    m = env.mean()
    if m <= 0:
        return 0.0
    return float(((env - m) ** 2).mean() / (m * m))


def phase_variance_dqpsk(iq: np.ndarray) -> float:
    """Variance of fourth-power phase — low for π/4-DQPSK (discrete constellation)."""
    if iq.size < 8:
        return 0.0
    env = np.abs(iq).mean()
    if env <= 0:
        return 0.0
    norm = iq / (env + 1e-12)
    ph4 = np.angle(norm ** 4)
    return float(np.var(ph4))
