"""Detection-layer unit tests."""

from __future__ import annotations

import numpy as np

from dsd.wideband.detect import ca_cfar, group_peaks
from dsd.wideband.detect.psd import averaged_psd, psd_freqs


def test_cfar_detects_single_tone():
    fs = 1_000_000.0
    n = 16384
    t = np.arange(n) / fs
    sig = 0.1 * np.exp(2j * np.pi * 100_000 * t) + 0.01 * (
        np.random.default_rng(0).standard_normal(n)
        + 1j * np.random.default_rng(1).standard_normal(n)
    )
    psd = averaged_psd([sig.astype(np.complex64)], nperseg=1024, nav=1)
    mask = ca_cfar(psd, guard=4, train=32, pfa=1e-6)
    freqs = psd_freqs(1024, fs)
    groups = group_peaks(mask, freqs, psd, min_bins=1)
    assert groups, "expected at least one detection"
    centers = [g[2] for g in groups]
    assert any(abs(c - 100_000) < 5_000 for c in centers)


def test_cfar_zero_signal():
    psd = np.zeros(1024, dtype=np.float32) + 1e-10
    mask = ca_cfar(psd, guard=2, train=16, pfa=1e-4)
    assert not mask.any()
