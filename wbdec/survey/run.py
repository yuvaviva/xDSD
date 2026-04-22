"""Stage-2 entry point: read a SplitSet, produce a SurveyResult.

Streaming — never holds more than one frame's worth of samples in memory.
Classification is deferred: M1 emits events with unknown labels; M2 adds
per-channel snippet extraction and runs the classifier with proper baseband
samples. A rough-cut feature-based label is attached here using the frame
samples as a cheap proxy.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import List, Optional, Tuple

import numpy as np

from ..capture.splits import SplitSet
from ..capture.sigmf_view import VirtualSigMF, write_view_meta
from ..config import Config
from .cfar import ca_cfar_mask, group_peaks
from .psd_stream import freq_axis, welch_frame
from .schema import SurveyEvent, SurveyResult
from .tracker_burst import BurstTracker
from .tracker_continuous import ContinuousTracker


def _save_psd_png(path: str, avg_psd: np.ndarray, freqs_hz: np.ndarray,
                  num_events: int) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    db = 10.0 * np.log10(np.maximum(avg_psd, 1e-20))
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(freqs_hz / 1e6, db, linewidth=0.6)
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Power (dB, relative)")
    ax.set_title(f"wbdec survey — {num_events} events")
    ax.grid(True, linewidth=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def run_survey(cfg: Config, out_dir: Optional[str] = None) -> SurveyResult:
    """End-to-end survey over ``cfg.capture.folder``. Returns SurveyResult and
    writes ``survey.json`` + ``psd.png`` into ``out_dir`` (default ``cfg.out_dir``).
    """
    out_dir = out_dir or cfg.out_dir
    os.makedirs(out_dir, exist_ok=True)

    # 1. Stitch splits.
    ss = SplitSet.discover(
        folder=cfg.capture.folder,
        sample_rate_hz=cfg.capture.sample_rate_hz,
        center_hz=cfg.capture.center_hz,
        fmt=cfg.capture.format,
    )
    view = VirtualSigMF.from_split_set(ss)
    meta_path = write_view_meta(view, out_dir)

    # 2. Set up frames + axis.
    nperseg = cfg.survey.nperseg
    frame_samples = cfg.survey.frame_samples
    freqs = freq_axis(nperseg, ss.sample_rate_hz, ss.center_hz)
    frame_period_s = frame_samples / ss.sample_rate_hz

    cont = ContinuousTracker(
        frame_period_s=frame_period_s,
        min_persist_frames=cfg.survey.min_persist_frames,
        max_absent_frames=cfg.survey.max_absent_frames,
        merge_tol_hz=cfg.survey.merge_freq_tol_hz,
    )
    burst = BurstTracker(
        frame_period_s=frame_period_s,
        window_frames=cfg.survey.burst_window_frames,
        min_duty_cycle=cfg.survey.burst_min_duty_cycle,
        merge_tol_hz=cfg.survey.merge_freq_tol_hz,
    )

    # 3. Streaming loop.
    min_bw_bins = max(1, int(cfg.survey.min_bw_hz * nperseg / ss.sample_rate_hz))
    max_bw_bins = max(min_bw_bins, int(cfg.survey.max_bw_hz * nperseg / ss.sample_rate_hz))

    running_psd = np.zeros(nperseg, dtype=np.float64)
    num_frames = 0
    buf = np.empty(0, dtype=np.complex64)
    for _, _, chunk in ss.iter_chunks(cfg.capture.chunk_samples):
        buf = np.concatenate([buf, chunk]) if buf.size else chunk
        while buf.size >= frame_samples:
            frame = buf[:frame_samples]
            buf = buf[frame_samples:]
            psd = welch_frame(frame, nperseg, overlap=cfg.survey.welch_overlap)
            running_psd += psd
            num_frames += 1
            mask = ca_cfar_mask(psd, cfg.survey.cfar_guard, cfg.survey.cfar_train,
                                cfg.survey.cfar_pfa)
            groups = group_peaks(mask, freqs, psd,
                                 min_bw_bins=min_bw_bins, max_bw_bins=max_bw_bins)
            detections: List[Tuple[float, float, float, float]] = []
            for lo, hi, center, bw, peak in groups:
                noise_band = np.concatenate([
                    psd[max(0, lo - cfg.survey.cfar_train): lo],
                    psd[hi + 1: hi + 1 + cfg.survey.cfar_train],
                ])
                noise = float(noise_band.mean()) if noise_band.size else 1e-20
                detections.append((center, bw, peak, noise))
            cont.update(num_frames - 1, detections)
            burst.update(num_frames - 1, detections)

    # Drain any residual < frame_samples.
    if buf.size >= nperseg:
        psd = welch_frame(buf, nperseg, overlap=cfg.survey.welch_overlap)
        running_psd += psd
        num_frames += 1

    cont.flush()
    burst.flush()

    events: List[SurveyEvent] = []
    events.extend(cont.events())
    events.extend(burst.events())
    events.sort(key=lambda e: (e.t_start_s, e.center_hz))

    avg_psd = (running_psd / max(num_frames, 1)).astype(np.float32)
    _save_psd_png(os.path.join(out_dir, "psd.png"), avg_psd, freqs,
                  len(events))

    result = SurveyResult(
        capture_meta_path=meta_path,
        sample_rate_hz=ss.sample_rate_hz,
        center_hz=ss.center_hz,
        duration_s=ss.duration_s,
        num_frames=num_frames,
        frame_period_s=frame_period_s,
        events=events,
        gaps=[asdict(g) for g in ss.gaps],
    )
    result.write_json(os.path.join(out_dir, "survey.json"))
    return result
