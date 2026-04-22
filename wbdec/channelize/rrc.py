"""Root-raised-cosine filter taps (used as the TETRA matched filter)."""

from __future__ import annotations

import numpy as np


def rrc_taps(sample_rate_hz: float, symbol_rate_hz: float,
             rolloff: float = 0.35, num_symbols: int = 8
             ) -> np.ndarray:
    """Generate an RRC filter impulse response with unit peak energy.

    ``num_symbols`` is the filter span in symbol periods (total taps ≈
    num_symbols * sps + 1).
    """
    sps = sample_rate_hz / symbol_rate_hz
    n = int(round(num_symbols * sps))
    if n % 2 == 0:
        n += 1
    t = (np.arange(n) - (n - 1) // 2) / sps
    beta = rolloff
    h = np.zeros(n, dtype=np.float64)
    for i, ti in enumerate(t):
        if abs(ti) < 1e-9:
            h[i] = 1.0 - beta + 4.0 * beta / np.pi
        elif abs(abs(ti) - 1.0 / (4.0 * beta)) < 1e-9:
            h[i] = (beta / np.sqrt(2.0)) * (
                (1.0 + 2.0 / np.pi) * np.sin(np.pi / (4.0 * beta))
                + (1.0 - 2.0 / np.pi) * np.cos(np.pi / (4.0 * beta))
            )
        else:
            num = np.sin(np.pi * ti * (1.0 - beta)) + 4.0 * beta * ti * np.cos(
                np.pi * ti * (1.0 + beta))
            den = np.pi * ti * (1.0 - (4.0 * beta * ti) ** 2)
            h[i] = num / den
    h /= np.sqrt(np.sum(h ** 2))
    return h.astype(np.float32)
