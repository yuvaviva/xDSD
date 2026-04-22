"""Cell-averaging CFAR over a 1-D PSD + group-by-run peak detector."""

from __future__ import annotations

from typing import List, Tuple

import numpy as np


def ca_cfar_mask(psd: np.ndarray, guard: int, train: int, pfa: float
                 ) -> np.ndarray:
    """Return a boolean mask where ``psd`` exceeds a local CFAR threshold.

    Cell-averaging CFAR: threshold = α · mean(train cells) with α derived
    from the desired probability of false-alarm.  Training cells on both
    sides of the cell under test, excluding ``guard`` cells.
    """
    n = psd.size
    if n < 2 * (guard + train) + 1:
        return np.zeros(n, dtype=bool)
    kernel = np.zeros(2 * (guard + train) + 1, dtype=np.float32)
    kernel[:train] = 1.0
    kernel[-train:] = 1.0
    kernel /= (2.0 * train)
    noise = np.convolve(psd, kernel, mode="same")
    alpha = 2.0 * train * (pfa ** (-1.0 / (2.0 * train)) - 1.0)
    return psd > alpha * noise


def group_peaks(mask: np.ndarray, freqs: np.ndarray, psd: np.ndarray,
                min_bw_bins: int = 2, max_bw_bins: int = 4096
                ) -> List[Tuple[int, int, float, float, float]]:
    """Group consecutive CFAR hits into (lo_bin, hi_bin, center_hz, bw_hz, peak_lin).

    The center frequency is taken at the peak bin of each run to avoid bias
    from asymmetric sidebands.
    """
    out: List[Tuple[int, int, float, float, float]] = []
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
        if min_bw_bins <= w <= max_bw_bins:
            lo, hi = i, j - 1
            pk = lo + int(np.argmax(psd[lo: hi + 1]))
            center = float(freqs[pk])
            bw = float(freqs[hi] - freqs[lo])
            out.append((lo, hi, center, bw, float(psd[pk])))
        i = j
    return out
