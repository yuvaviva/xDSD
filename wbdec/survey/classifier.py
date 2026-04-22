"""Feature-based protocol classifier with Bayesian fusion of per-feature scores.

Default is feature-only (no ONNX dependency). The CNN classifier is a future
``[ml]`` extra that would replace ``classify_from_iq`` — the interface stays
the same so downstream code doesn't change.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np

from .features import ClassifyFeatures, extract_all


PROTOCOLS = ("p25_c4fm", "dmr", "dpmr", "tetra", "analog_fm", "unknown")


def _triangle(x: float, lo: float, peak: float, hi: float) -> float:
    if x <= lo or x >= hi:
        return 0.0
    if x <= peak:
        return (x - lo) / max(peak - lo, 1e-9)
    return (hi - x) / max(hi - peak, 1e-9)


def _score_p25_c4fm(f: ClassifyFeatures) -> float:
    bw = _triangle(f.occupied_bw_hz,  7_000, 12_500, 18_000)
    sr = _triangle(f.symbol_rate_hz,  3_500,  4_800,  6_000)
    lvl = 1.0 if f.level_count == 4 else (0.5 if f.level_count >= 3 else 0.2)
    env = 1.0 if f.env_var_norm < 0.05 else 0.2
    return 0.30 * bw + 0.35 * sr + 0.20 * lvl + 0.15 * env


def _score_dmr(f: ClassifyFeatures) -> float:
    # Same carrier width + 4FSK as P25 — disambiguation happens via the
    # burst-vs-continuous tracker kind, not via PSD features alone.
    return _score_p25_c4fm(f) * 0.98


def _score_dpmr(f: ClassifyFeatures) -> float:
    bw = _triangle(f.occupied_bw_hz,  3_500,  6_250, 10_000)
    sr = _triangle(f.symbol_rate_hz,  1_800,  2_400,  3_200)
    lvl = 1.0 if f.level_count == 4 else (0.5 if f.level_count >= 3 else 0.2)
    env = 1.0 if f.env_var_norm < 0.05 else 0.2
    return 0.30 * bw + 0.35 * sr + 0.20 * lvl + 0.15 * env


def _score_tetra(f: ClassifyFeatures) -> float:
    bw = _triangle(f.occupied_bw_hz, 18_000, 25_000, 32_000)
    sr = _triangle(f.symbol_rate_hz, 14_000, 18_000, 22_000)
    env = 1.0 if f.env_var_norm > 0.05 else 0.2            # linear modulation
    ph = 1.0 if f.phase4_var < 1.0 else 0.3                # discrete constellation
    return 0.25 * bw + 0.30 * sr + 0.20 * env + 0.25 * ph


def _score_analog_fm(f: ClassifyFeatures) -> float:
    # Wide (~10-15 kHz), no discrete levels, near-constant envelope, no cyclic peak.
    bw = _triangle(f.occupied_bw_hz, 8_000, 12_000, 16_000)
    no_cyclic = 1.0 if f.symbol_rate_hz < 1_500 else 0.2
    env = 1.0 if f.env_var_norm < 0.05 else 0.3
    lvl = 1.0 if f.level_count <= 2 else 0.3
    return 0.30 * bw + 0.35 * no_cyclic + 0.20 * env + 0.15 * lvl


def classify_from_features(f: ClassifyFeatures, kind: str = "continuous"
                           ) -> Tuple[str, float]:
    scores = {
        "p25_c4fm":  _score_p25_c4fm(f),
        "dmr":       _score_dmr(f),
        "dpmr":      _score_dpmr(f),
        "tetra":     _score_tetra(f),
        "analog_fm": _score_analog_fm(f),
    }
    # Give burst events a 10% bump towards TDMA labels.
    if kind == "burst":
        scores["dmr"] *= 1.10
        scores["tetra"] *= 1.10
    label = max(scores, key=lambda k: scores[k])
    conf = scores[label]
    if conf < 0.25:
        return "unknown", float(conf)
    return label, float(conf)


def classify_from_iq(iq_baseband: np.ndarray, sample_rate_hz: float,
                     fm_demod: np.ndarray, kind: str = "continuous"
                     ) -> Tuple[str, float, ClassifyFeatures]:
    f = extract_all(iq_baseband, sample_rate_hz, fm_demod)
    label, conf = classify_from_features(f, kind=kind)
    return label, conf, f
