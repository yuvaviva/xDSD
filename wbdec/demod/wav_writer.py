"""Minimal WAV helpers used as the decoder subprocess I/O format."""

from __future__ import annotations

import os
import wave
from typing import Optional

import numpy as np


def write_mono_int16_wav(path: str, samples: np.ndarray,
                         sample_rate_hz: int) -> None:
    """Write a mono 16-bit PCM WAV. Input is float ±1-ish; clipped safely."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    s = np.clip(samples.astype(np.float32, copy=False), -1.0, 1.0)
    pcm = (s * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate_hz))
        wf.writeframes(pcm.tobytes())


def read_wav_as_float(path: str) -> tuple[Optional[np.ndarray], int]:
    """Return (float32 samples, sample_rate). ``samples`` is None if unreadable."""
    if not os.path.exists(path) or os.path.getsize(path) < 44:
        return None, 0
    try:
        with wave.open(path, "rb") as wf:
            n = wf.getnframes()
            sr = wf.getframerate()
            sw = wf.getsampwidth()
            nc = wf.getnchannels()
            raw = wf.readframes(n)
    except wave.Error:
        return None, 0
    if sw == 2:
        arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 1:
        arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
               - 128.0) / 128.0
    else:
        return None, 0
    if nc == 2:
        # downmix to mono
        arr = 0.5 * (arr[0::2] + arr[1::2])
    return arr.astype(np.float32), sr
