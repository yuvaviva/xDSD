"""Quadrature FM discriminator."""

from __future__ import annotations

import numpy as np


def fm_discriminator(iq: np.ndarray, gain: float = 1.0) -> np.ndarray:
    """Phase-difference FM demodulator.

    Output is instantaneous frequency in rad/sample, scaled by ``gain``.
    DSD-family decoders expect float samples roughly in ±1 range; pick
    ``gain`` so typical peak deviation hits ~0.6-0.8.
    """
    if iq.size < 2:
        return np.zeros(0, dtype=np.float32)
    diff = iq[1:] * np.conj(iq[:-1])
    return (np.angle(diff) * gain).astype(np.float32)
