"""Cell-averaging CFAR peak detector over a 1-D PSD."""

from __future__ import annotations

from typing import List, Tuple

import numpy as np


def ca_cfar(psd: np.ndarray, guard: int, train: int, pfa: float
            ) -> np.ndarray:
    """Return a boolean mask where psd exceeds the local CFAR threshold.

    Uses a cell-averaging CFAR: threshold = alpha * mean(train cells) where
    alpha is derived from the desired probability of false alarm. Training
    cells on both sides of the cell under test, excluding `guard` cells.
    """
    n = psd.size
    if n < 2 * (guard + train) + 1:
        return np.zeros(n, dtype=bool)
    kernel = np.zeros(2 * (guard + train) + 1, dtype=np.float32)
    kernel[:train] = 1.0
    kernel[-train:] = 1.0
    kernel /= 2.0 * train
    noise = np.convolve(psd, kernel, mode="same")
    alpha = 2.0 * train * (pfa ** (-1.0 / (2.0 * train)) - 1.0)
    threshold = alpha * noise
    return psd > threshold


def group_peaks(mask: np.ndarray, freqs: np.ndarray, psd: np.ndarray,
                min_bins: int = 2, max_bins: int = 4096
                ) -> List[Tuple[int, int, float, float]]:
    """Group consecutive CFAR-flagged bins into (lo, hi, center_hz, bw_hz, pk).

    Returned tuples: (bin_lo, bin_hi, center_hz, bw_hz). `psd` is used only to
    locate the peak bin inside a group for better center-frequency estimates.
    """
    out: List[Tuple[int, int, float, float]] = []
    n = mask.size
    i = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        w = j - i
        if min_bins <= w <= max_bins:
            lo, hi = i, j - 1
            pk = lo + int(np.argmax(psd[lo: hi + 1]))
            center = float(freqs[pk])
            bw = float(freqs[hi] - freqs[lo])
            out.append((lo, hi, center, bw))
        i = j
    return out
