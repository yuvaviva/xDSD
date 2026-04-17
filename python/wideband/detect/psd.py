"""Averaged power spectral density over streamed complex IQ."""

from __future__ import annotations

from typing import Iterable, Iterator, Tuple

import numpy as np


def _welch_frame(x: np.ndarray, nperseg: int, window: np.ndarray) -> np.ndarray:
    """One averaged PSD frame from an array whose length is a multiple of nperseg."""
    n_segs = x.size // nperseg
    if n_segs == 0:
        return np.zeros(nperseg, dtype=np.float32)
    x = x[: n_segs * nperseg].reshape(n_segs, nperseg)
    xw = x * window
    sp = np.fft.fftshift(np.fft.fft(xw, axis=1), axes=1)
    psd = (sp.real ** 2 + sp.imag ** 2).mean(axis=0)
    norm = (window ** 2).sum() * n_segs
    return (psd / norm).astype(np.float32)


def stream_frames(blocks: Iterable[np.ndarray], nperseg: int, nav: int
                  ) -> Iterator[Tuple[int, np.ndarray]]:
    """Group streamed IQ blocks into frames of nperseg*nav samples; yield PSDs.

    Each yielded tuple is (frame_index, psd_linear_power).
    Remaining samples shorter than nperseg are dropped with the final frame.
    """
    window = np.hanning(nperseg).astype(np.float32)
    buf = np.empty(0, dtype=np.complex64)
    want = nperseg * nav
    idx = 0
    for blk in blocks:
        buf = np.concatenate([buf, blk]) if buf.size else blk
        while buf.size >= want:
            frame = buf[:want]
            buf = buf[want:]
            yield idx, _welch_frame(frame, nperseg, window)
            idx += 1
    if buf.size >= nperseg:
        yield idx, _welch_frame(buf, nperseg, window)


def averaged_psd(blocks: Iterable[np.ndarray], nperseg: int, nav: int
                 ) -> np.ndarray:
    """Return a single averaged PSD across the whole stream."""
    accum = np.zeros(nperseg, dtype=np.float64)
    n = 0
    for _, psd in stream_frames(blocks, nperseg, nav):
        accum += psd
        n += 1
    if n == 0:
        return np.zeros(nperseg, dtype=np.float32)
    return (accum / n).astype(np.float32)


def psd_freqs(nperseg: int, sample_rate: float, center_hz: float = 0.0
              ) -> np.ndarray:
    return center_hz + np.fft.fftshift(np.fft.fftfreq(nperseg, 1.0 / sample_rate))
