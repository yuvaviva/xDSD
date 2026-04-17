"""Quadrature FM discriminator."""

from __future__ import annotations

import numpy as np


def fm_discriminator(iq: np.ndarray, gain: float = 1.0) -> np.ndarray:
    """Compute instantaneous frequency via phase-difference trick.

    Output is in rad/sample * gain. Multiply by sample_rate/(2*pi) to get Hz.
    For feeding DSD (which expects ±1 FM-demod float), choose gain so that the
    peak deviation of the target protocol maps near ±1 at the target rate.
    """
    if iq.size < 2:
        return np.zeros(0, dtype=np.float32)
    diff = iq[1:] * np.conj(iq[:-1])
    return (np.angle(diff) * gain).astype(np.float32)
