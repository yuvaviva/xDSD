"""WAV / JSON / spectrogram writers."""

from __future__ import annotations

import json
import os
import wave
from typing import Any, Dict

import numpy as np


def write_wav_int16(path: str, samples: np.ndarray, sample_rate: int) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        pcm = np.asarray(samples, dtype=np.int16).tobytes()
        wf.writeframes(pcm)


def write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2, default=_json_default)


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def write_spectrogram_png(path: str, psd_db: np.ndarray, freqs_hz: np.ndarray,
                          title: str = "wideband PSD") -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return  # matplotlib is optional
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(freqs_hz / 1e6, psd_db, linewidth=0.6)
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Power (dB)")
    ax.set_title(title)
    ax.grid(True, linewidth=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
