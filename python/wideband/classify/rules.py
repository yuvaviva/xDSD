"""Rule-based classifier mapping features → protocol label + confidence."""

from __future__ import annotations

from typing import Tuple

import numpy as np

from .features import (
    ClassifyFeatures,
    estimate_occupied_bandwidth,
    estimate_symbol_rate,
    level_histogram,
    peak_deviation,
    envelope_variance,
    phase_variance_dqpsk,
)


PROTOCOLS = ("p25_c4fm", "dmr", "dpmr", "tetra", "unknown")


def _extract_features(iq_baseband: np.ndarray, sample_rate: float,
                      demod: np.ndarray) -> ClassifyFeatures:
    return ClassifyFeatures(
        occupied_bw_hz=estimate_occupied_bandwidth(iq_baseband, sample_rate),
        symbol_rate_est_hz=estimate_symbol_rate(iq_baseband, sample_rate),
        level_count=level_histogram(demod)[0],
        peak_deviation_hz=peak_deviation(demod, sample_rate),
        const_phase_variance=phase_variance_dqpsk(iq_baseband),
        envelope_variance=envelope_variance(iq_baseband),
    )


def _score_p25(f: ClassifyFeatures) -> float:
    # 12.5 kHz FM, 4800 sym/s 4FSK, ~1.8 kHz peak dev, near-constant envelope.
    bw = _triangle(f.occupied_bw_hz, 8_000, 12_500, 18_000)
    sr = _triangle(f.symbol_rate_est_hz, 3_500, 4_800, 6_000)
    lvl = 1.0 if f.level_count == 4 else 0.4
    env = 1.0 if f.envelope_variance < 0.05 else 0.3
    return 0.30 * bw + 0.35 * sr + 0.20 * lvl + 0.15 * env


def _score_dmr(f: ClassifyFeatures) -> float:
    # Same bandwidth + symbol rate as P25 but bursted (TDMA). Envelope still near-constant.
    return _score_p25(f) * 0.95  # tie-break by burst detection in decoder


def _score_dpmr(f: ClassifyFeatures) -> float:
    # 6.25 kHz FDMA 4FSK 2400 sym/s.
    bw = _triangle(f.occupied_bw_hz, 3_500, 6_250, 9_000)
    sr = _triangle(f.symbol_rate_est_hz, 1_800, 2_400, 3_200)
    lvl = 1.0 if f.level_count == 4 else 0.4
    env = 1.0 if f.envelope_variance < 0.05 else 0.3
    return 0.30 * bw + 0.35 * sr + 0.20 * lvl + 0.15 * env


def _score_tetra(f: ClassifyFeatures) -> float:
    # 25 kHz, 18 ksym/s, π/4-DQPSK — non-constant envelope, discrete 4th-power phase.
    bw = _triangle(f.occupied_bw_hz, 18_000, 25_000, 32_000)
    sr = _triangle(f.symbol_rate_est_hz, 14_000, 18_000, 22_000)
    env = 1.0 if f.envelope_variance > 0.05 else 0.2
    ph = 1.0 if f.const_phase_variance < 0.5 else 0.3
    return 0.30 * bw + 0.35 * sr + 0.15 * env + 0.20 * ph


def _triangle(x: float, lo: float, peak: float, hi: float) -> float:
    if x <= lo or x >= hi:
        return 0.0
    if x <= peak:
        return (x - lo) / max(peak - lo, 1e-9)
    return (hi - x) / max(hi - peak, 1e-9)


def classify_event(iq_baseband: np.ndarray, sample_rate_baseband: float,
                   demod: np.ndarray) -> Tuple[str, float, ClassifyFeatures]:
    """Return (label, confidence, features)."""
    f = _extract_features(iq_baseband, sample_rate_baseband, demod)
    scores = {
        "p25_c4fm": _score_p25(f),
        "dmr": _score_dmr(f),
        "dpmr": _score_dpmr(f),
        "tetra": _score_tetra(f),
    }
    label = max(scores, key=lambda k: scores[k])
    conf = scores[label]
    if conf < 0.3:
        return "unknown", float(conf), f
    return label, float(conf), f
