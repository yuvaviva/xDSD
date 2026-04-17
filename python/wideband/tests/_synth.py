"""Synthesis helpers for unit / integration tests."""

from __future__ import annotations

import os
from typing import Iterable, Tuple

import numpy as np


def synth_4fsk(n_samples: int, sample_rate: float, symbol_rate: float,
               peak_dev_hz: float, seed: int = 0) -> np.ndarray:
    """Generate a 4FSK complex baseband signal at DC."""
    rng = np.random.default_rng(seed)
    sps = int(round(sample_rate / symbol_rate))
    n_syms = n_samples // sps + 1
    levels = np.array([-3, -1, 1, 3], dtype=np.float32)
    symbols = levels[rng.integers(0, 4, size=n_syms)]
    # Rectangular symbol shaping is fine for classifier tests.
    freq_offsets = np.repeat(symbols, sps)[:n_samples] * (peak_dev_hz / 3.0)
    phase = 2.0 * np.pi * np.cumsum(freq_offsets) / sample_rate
    return np.exp(1j * phase).astype(np.complex64)


def synth_pi4_dqpsk(n_samples: int, sample_rate: float, symbol_rate: float,
                    seed: int = 0) -> np.ndarray:
    """Minimal π/4-DQPSK for TETRA classifier tests (not a full waveform)."""
    rng = np.random.default_rng(seed)
    sps = int(round(sample_rate / symbol_rate))
    n_syms = n_samples // sps + 1
    rotations = np.array([1, 3, 5, 7], dtype=np.float32) * np.pi / 4.0
    drot = rotations[rng.integers(0, 4, size=n_syms)]
    phases = np.cumsum(drot)
    symbols = np.exp(1j * phases)
    sig = np.repeat(symbols, sps)[:n_samples].astype(np.complex64)
    # Add a bit of envelope variation to differentiate from FM.
    env = 0.5 + 0.5 * np.abs(np.sin(2 * np.pi * np.arange(n_samples) / 1024.0))
    return (sig * env).astype(np.complex64)


def make_wideband_capture(path: str, sample_rate: float, duration_s: float,
                          carriers: Iterable[Tuple[str, float, float]],
                          noise_rms: float = 0.02, seed: int = 1) -> str:
    """Build a synthetic 10 MHz wideband HackRF int8 capture.

    carriers: iterable of (type, offset_hz, amplitude). type ∈ {"p25","dmr","tetra","dpmr"}.
    """
    n = int(round(sample_rate * duration_s))
    rng = np.random.default_rng(seed)
    iq = (rng.standard_normal(n) + 1j * rng.standard_normal(n)).astype(np.complex64)
    iq *= noise_rms
    t = np.arange(n, dtype=np.float32)
    for typ, off, amp in carriers:
        if typ == "p25":
            s = synth_4fsk(n, sample_rate, 4800, 1800, seed=seed + 1)
        elif typ == "dmr":
            s = synth_4fsk(n, sample_rate, 4800, 1944, seed=seed + 2)
        elif typ == "dpmr":
            s = synth_4fsk(n, sample_rate, 2400, 1050, seed=seed + 3)
        elif typ == "tetra":
            s = synth_pi4_dqpsk(n, sample_rate, 18000, seed=seed + 4)
        else:
            raise ValueError(typ)
        s = s * np.exp(2j * np.pi * off * t / sample_rate).astype(np.complex64)
        iq += (amp * s).astype(np.complex64)
    # Quantize to int8 for HackRF-style output.
    i8 = np.clip(np.real(iq) * 127.0, -127, 127).astype(np.int8)
    q8 = np.clip(np.imag(iq) * 127.0, -127, 127).astype(np.int8)
    interleaved = np.empty(n * 2, dtype=np.int8)
    interleaved[0::2] = i8
    interleaved[1::2] = q8
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    interleaved.tofile(path)
    return path
