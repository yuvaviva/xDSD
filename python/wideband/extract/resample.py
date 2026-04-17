"""Rational resampling to a target sample rate."""

from __future__ import annotations

import numpy as np


def resample_to(x: np.ndarray, src_rate: float, dst_rate: float) -> np.ndarray:
    if abs(src_rate - dst_rate) < 1.0:
        return x
    from scipy.signal import resample_poly
    up = int(round(dst_rate))
    down = int(round(src_rate))
    g = _gcd(up, down)
    up, down = max(up // g, 1), max(down // g, 1)
    return resample_poly(x, up, down).astype(x.dtype)


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a
