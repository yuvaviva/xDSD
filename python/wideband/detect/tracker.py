"""Temporal hysteresis: aggregate per-frame CFAR hits into SignalEvents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from .events import SignalEvent


@dataclass
class _Track:
    center_hz: float
    bw_hz: float
    first_frame: int
    last_frame: int
    peak_power: float
    noise_power: float
    hits: int
    gap_frames: int = 0


class EventTracker:
    """Merge per-frame detections over time into SignalEvents with hysteresis.

    A track is opened when a detection appears; it survives up to
    `max_absent_frames` with no overlapping detection; it is emitted only if
    it accumulated at least `min_persist_frames` hits.
    """

    def __init__(self, frame_period_s: float, min_persist_frames: int,
                 max_absent_frames: int, merge_tol_hz: float = 5_000.0):
        self.frame_period_s = frame_period_s
        self.min_persist = min_persist_frames
        self.max_absent = max_absent_frames
        self.merge_tol = merge_tol_hz
        self._tracks: List[_Track] = []
        self._finalized: List[_Track] = []

    def _match(self, center_hz: float) -> int:
        for i, t in enumerate(self._tracks):
            if abs(t.center_hz - center_hz) <= max(self.merge_tol, t.bw_hz):
                return i
        return -1

    def update(self, frame_idx: int,
               detections: List[Tuple[float, float, float, float]]) -> None:
        """detections: list of (center_hz, bw_hz, peak_power_lin, noise_power_lin)."""
        seen = set()
        for center, bw, pk, noise in detections:
            i = self._match(center)
            if i < 0:
                self._tracks.append(_Track(
                    center_hz=center, bw_hz=bw,
                    first_frame=frame_idx, last_frame=frame_idx,
                    peak_power=pk, noise_power=max(noise, 1e-20),
                    hits=1, gap_frames=0,
                ))
                seen.add(len(self._tracks) - 1)
            else:
                t = self._tracks[i]
                t.last_frame = frame_idx
                t.hits += 1
                t.gap_frames = 0
                t.peak_power = max(t.peak_power, pk)
                t.noise_power = (t.noise_power + max(noise, 1e-20)) / 2.0
                # Slow-update center / bw with EMA to follow drift.
                t.center_hz = 0.8 * t.center_hz + 0.2 * center
                t.bw_hz = 0.8 * t.bw_hz + 0.2 * bw
                seen.add(i)
        keep: List[_Track] = []
        for i, t in enumerate(self._tracks):
            if i in seen:
                keep.append(t)
            else:
                t.gap_frames += 1
                if t.gap_frames > self.max_absent:
                    self._finalized.append(t)
                else:
                    keep.append(t)
        self._tracks = keep

    def flush(self) -> None:
        self._finalized.extend(self._tracks)
        self._tracks = []

    def events(self) -> List[SignalEvent]:
        events: List[SignalEvent] = []
        for t in self._finalized:
            if t.hits < self.min_persist:
                continue
            snr = 10.0 * np.log10(t.peak_power / t.noise_power)
            events.append(SignalEvent(
                center_hz=t.center_hz,
                bw_hz=t.bw_hz,
                t_start=t.first_frame * self.frame_period_s,
                t_end=(t.last_frame + 1) * self.frame_period_s,
                snr_db=float(snr),
                peak_power_db=float(10.0 * np.log10(max(t.peak_power, 1e-20))),
            ))
        return events
