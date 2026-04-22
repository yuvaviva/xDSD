"""Feature extractors used by the classifier.

All features operate on baseband complex IQ snippets (not FM-demod scalars)
centered at DC. The caller is expected to have extracted a short baseband
chunk (e.g. 32k samples) of the candidate channel at an appropriate sample
rate (48-72 kHz).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ClassifyFeatures:
    occupied_bw_hz: float
    symbol_rate_hz: float
    level_count: int
    peak_dev_hz: float
    env_var_norm: float          # variance of |x| normalised by mean |x|^2
    phase4_var: float            # variance of angle(x**4); low = π/4-DQPSK-like


def estimate_occupied_bandwidth(iq: np.ndarray, sample_rate_hz: float,
                                energy_fraction: float = 0.99) -> float:
    n = min(len(iq), 1 << 15)
    if n < 256:
        return 0.0
    x = iq[:n] * np.hanning(n).astype(np.float32)
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
    return float((hi_bin - lo_bin) * sample_rate_hz / n)


def estimate_symbol_rate_cyclo(iq: np.ndarray, sample_rate_hz: float,
                               f_min_hz: float = 1000.0,
                               f_max_hz: float = 25000.0) -> float:
    """Symbol-rate estimator via the |x|^2 cyclostationary spectrum peak."""
    n = min(len(iq), 1 << 16)
    if n < 1024:
        return 0.0
    x2 = np.abs(iq[:n]) ** 2
    x2 = x2 - x2.mean()
    sp = np.fft.rfft(x2 * np.hanning(n))
    freqs = np.fft.rfftfreq(n, 1.0 / sample_rate_hz)
    mask = (freqs >= f_min_hz) & (freqs <= f_max_hz)
    if not mask.any():
        return 0.0
    peak = int(np.argmax(np.abs(sp[mask])))
    return float(freqs[mask][peak])


def level_histogram_peaks(demod: np.ndarray, n_bins: int = 64) -> int:
    """Count dominant histogram peaks on an FM-demod signal.

    2 ≈ 2FSK, 4 ≈ 4FSK. Returns 0 if signal is too flat.
    """
    if demod.size == 0:
        return 0
    lo, hi = np.percentile(demod, [1, 99])
    if hi <= lo:
        return 0
    h, _ = np.histogram(demod, bins=n_bins, range=(lo, hi))
    hs = np.convolve(h, np.ones(3) / 3.0, mode="same")
    thr = hs.max() * 0.25
    peaks = 0
    for i in range(1, len(hs) - 1):
        if hs[i] > thr and hs[i] >= hs[i - 1] and hs[i] >= hs[i + 1]:
            peaks += 1
    return peaks


def envelope_variance(iq: np.ndarray) -> float:
    """Normalised envelope variance: low for constant-envelope (FM),
    high for non-constant (PSK like π/4-DQPSK).
    """
    if iq.size == 0:
        return 0.0
    env = np.abs(iq)
    m = float(env.mean())
    if m <= 0:
        return 0.0
    return float(((env - m) ** 2).mean() / (m * m))


def phase_fourth_power_variance(iq: np.ndarray) -> float:
    """Variance of the fourth-power phase of the unit-normalised signal.

    Small for QPSK-family constellations (including π/4-DQPSK when
    preceded by RRC matched filtering); larger for FSK.
    """
    if iq.size < 8:
        return 0.0
    env = np.abs(iq).mean()
    if env <= 0:
        return 0.0
    norm = iq / (env + 1e-12)
    ph4 = np.angle(norm ** 4)
    return float(np.var(ph4))


def extract_all(iq_baseband: np.ndarray, sample_rate_hz: float,
                demod: np.ndarray) -> ClassifyFeatures:
    return ClassifyFeatures(
        occupied_bw_hz=estimate_occupied_bandwidth(iq_baseband, sample_rate_hz),
        symbol_rate_hz=estimate_symbol_rate_cyclo(iq_baseband, sample_rate_hz),
        level_count=level_histogram_peaks(demod),
        peak_dev_hz=float(np.percentile(np.abs(demod), 95)
                          * sample_rate_hz / (2.0 * np.pi))
        if demod.size else 0.0,
        env_var_norm=envelope_variance(iq_baseband),
        phase4_var=phase_fourth_power_variance(iq_baseband),
    )
