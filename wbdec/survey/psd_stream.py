"""Streaming Welch PSD and frequency axis helpers."""

from __future__ import annotations

from typing import Iterable, Iterator, Tuple

import numpy as np


def welch_frame(samples: np.ndarray, nperseg: int, overlap: float = 0.5
                ) -> np.ndarray:
    """Welch-averaged PSD (linear power) over one time-frame.

    ``samples`` is complex; any length ≥ nperseg works.
    Returns an ``nperseg``-length array in fft-shifted order (DC at centre).
    """
    if samples.size < nperseg:
        return np.zeros(nperseg, dtype=np.float32)
    step = max(1, int(nperseg * (1.0 - overlap)))
    window = np.hanning(nperseg).astype(np.float32)
    win_energy = float((window ** 2).sum())
    n_segs = 1 + (samples.size - nperseg) // step
    accum = np.zeros(nperseg, dtype=np.float64)
    for k in range(n_segs):
        a = k * step
        seg = samples[a: a + nperseg] * window
        sp = np.fft.fftshift(np.fft.fft(seg))
        accum += (sp.real ** 2 + sp.imag ** 2)
    accum /= (win_energy * n_segs)
    return accum.astype(np.float32)


def freq_axis(nperseg: int, sample_rate_hz: float, center_hz: float = 0.0
              ) -> np.ndarray:
    """Absolute-frequency axis for a fft-shifted ``welch_frame`` output."""
    return center_hz + np.fft.fftshift(np.fft.fftfreq(nperseg, 1.0 / sample_rate_hz))


def stream_frames(chunks: Iterable[np.ndarray], frame_samples: int, nperseg: int,
                  overlap: float = 0.5
                  ) -> Iterator[Tuple[int, np.ndarray, np.ndarray]]:
    """Regroup streamed chunks into ``frame_samples``-length frames and yield
    ``(frame_index, psd, raw_frame_iq)``. Useful for both detection and
    subsequent feature extraction.

    Handles the case where chunks are smaller OR larger than the frame.
    """
    buf = np.empty(0, dtype=np.complex64)
    idx = 0
    for chunk in chunks:
        buf = np.concatenate([buf, chunk]) if buf.size else chunk
        while buf.size >= frame_samples:
            frame = buf[:frame_samples]
            buf = buf[frame_samples:]
            yield idx, welch_frame(frame, nperseg, overlap), frame
            idx += 1
    if buf.size >= nperseg:
        yield idx, welch_frame(buf, nperseg, overlap), buf
