"""Tiny synthesis helpers for unit / integration tests."""

from __future__ import annotations

import os
from typing import Iterable, Tuple

import numpy as np


def synth_4fsk(n: int, sample_rate_hz: float, symbol_rate_hz: float,
               peak_dev_hz: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    sps = max(1, int(round(sample_rate_hz / symbol_rate_hz)))
    n_syms = n // sps + 1
    levels = np.array([-3, -1, 1, 3], dtype=np.float32)
    symbols = levels[rng.integers(0, 4, size=n_syms)]
    freq = np.repeat(symbols, sps)[:n] * (peak_dev_hz / 3.0)
    phase = 2.0 * np.pi * np.cumsum(freq) / sample_rate_hz
    return np.exp(1j * phase).astype(np.complex64)


def synth_pi4_dqpsk(n: int, sample_rate_hz: float, symbol_rate_hz: float,
                    seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    sps = max(1, int(round(sample_rate_hz / symbol_rate_hz)))
    n_syms = n // sps + 1
    rotations = np.array([1, 3, 5, 7], dtype=np.float32) * np.pi / 4.0
    drot = rotations[rng.integers(0, 4, size=n_syms)]
    phases = np.cumsum(drot)
    sig = np.repeat(np.exp(1j * phases), sps)[:n]
    env = 0.5 + 0.5 * np.abs(np.sin(2 * np.pi * np.arange(n) / 1024.0))
    return (sig * env).astype(np.complex64)


def synth_bursty_4fsk(n: int, sample_rate_hz: float, symbol_rate_hz: float,
                      peak_dev_hz: float, burst_len_samples: int,
                      gap_len_samples: int, seed: int = 0) -> np.ndarray:
    """4FSK with rectangular bursts — crude TDMA simulant for DMR/TETRA."""
    base = synth_4fsk(n, sample_rate_hz, symbol_rate_hz, peak_dev_hz, seed=seed)
    gate = np.zeros(n, dtype=np.float32)
    k = 0
    while k < n:
        stop = min(k + burst_len_samples, n)
        gate[k:stop] = 1.0
        k = stop + gap_len_samples
    return (base * gate).astype(np.complex64)


def write_hackrf_int8(path: str, iq: np.ndarray) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    i = np.clip(iq.real * 127.0, -127, 127).astype(np.int8)
    q = np.clip(iq.imag * 127.0, -127, 127).astype(np.int8)
    il = np.empty(iq.size * 2, dtype=np.int8)
    il[0::2] = i
    il[1::2] = q
    il.tofile(path)
    return path


def make_wideband_split_capture(folder: str, sample_rate_hz: float,
                                duration_s: float, carriers: Iterable[Tuple],
                                noise_rms: float = 0.02, seed: int = 1,
                                n_splits: int = 1, file_prefix: str = "hackrf_"
                                ) -> list[str]:
    """Synthesise wideband IQ and split into N files as HackRF int8.

    carriers: iterable of (kind, offset_hz, amplitude) or
             (kind, offset_hz, amplitude, dict(extra)) where ``extra`` can
             hold ``burst_len`` / ``gap_len`` for bursty signals.
    """
    n = int(round(sample_rate_hz * duration_s))
    rng = np.random.default_rng(seed)
    iq = ((rng.standard_normal(n).astype(np.float32)
           + 1j * rng.standard_normal(n).astype(np.float32))
          * noise_rms).astype(np.complex64)
    t = np.arange(n, dtype=np.float32)
    for c in carriers:
        if len(c) == 3:
            kind, off, amp = c
            extra = {}
        else:
            kind, off, amp, extra = c
        if kind == "p25":
            s = synth_4fsk(n, sample_rate_hz, 4800, 1800, seed=seed + 1)
        elif kind == "dmr":
            # default to bursty
            bl = extra.get("burst_len", int(sample_rate_hz * 0.030))
            gl = extra.get("gap_len",   int(sample_rate_hz * 0.030))
            s = synth_bursty_4fsk(n, sample_rate_hz, 4800, 1944, bl, gl,
                                  seed=seed + 2)
        elif kind == "dpmr":
            s = synth_4fsk(n, sample_rate_hz, 2400, 1050, seed=seed + 3)
        elif kind == "tetra":
            s = synth_pi4_dqpsk(n, sample_rate_hz, 18000, seed=seed + 4)
        else:
            raise ValueError(kind)
        s = (s * np.exp(2j * np.pi * off * t / sample_rate_hz)).astype(np.complex64)
        iq = iq + (amp * s).astype(np.complex64)
    os.makedirs(folder, exist_ok=True)
    # Split into N equal chunks.
    chunk = n // n_splits
    paths: list[str] = []
    for k in range(n_splits):
        a = k * chunk
        b = n if k == n_splits - 1 else (k + 1) * chunk
        p = os.path.join(folder, f"{file_prefix}{k:04d}.iq")
        write_hackrf_int8(p, iq[a:b])
        paths.append(p)
    return paths
