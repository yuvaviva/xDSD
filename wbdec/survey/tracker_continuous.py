"""Continuous-emission tracker: aggregates per-frame CFAR hits into
SignalEvents for non-bursty signals (P25 conventional voice, dPMR,
analog FM). TDMA bursts are the ``BurstTracker``'s job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from .schema import SurveyEvent


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


class ContinuousTracker:
    def __init__(self, frame_period_s: float, min_persist_frames: int,
                 max_absent_frames: int, merge_tol_hz: float):
        self.frame_period_s = frame_period_s
        self.min_persist = min_persist_frames
        self.max_absent = max_absent_frames
        self.merge_tol = merge_tol_hz
        self._tracks: List[_Track] = []
        self._finalized: List[_Track] = []

    def _match(self, center_hz: float, bw_hz: float) -> int:
        for i, t in enumerate(self._tracks):
            tol = max(self.merge_tol, bw_hz, t.bw_hz)
            if abs(t.center_hz - center_hz) <= tol:
                return i
        return -1

    def update(self, frame_idx: int,
               detections: List[Tuple[float, float, float, float]]) -> None:
        """detections: list of (center_hz, bw_hz, peak_power_lin, noise_power_lin)."""
        seen = set()
        for center, bw, pk, noise in detections:
            i = self._match(center, bw)
            if i < 0:
                self._tracks.append(_Track(
                    center_hz=center, bw_hz=bw,
                    first_frame=frame_idx, last_frame=frame_idx,
                    peak_power=pk, noise_power=max(noise, 1e-20),
                    hits=1,
                ))
                seen.add(len(self._tracks) - 1)
            else:
                t = self._tracks[i]
                t.last_frame = frame_idx
                t.hits += 1
                t.gap_frames = 0
                t.peak_power = max(t.peak_power, pk)
                t.noise_power = 0.8 * t.noise_power + 0.2 * max(noise, 1e-20)
                t.center_hz = 0.85 * t.center_hz + 0.15 * center
                t.bw_hz = max(t.bw_hz, bw)
                seen.add(i)
        keep: List[_Track] = []
        for i, t in enumerate(self._tracks):
            if i in seen:
                keep.append(t)
                continue
            t.gap_frames += 1
            if t.gap_frames > self.max_absent:
                self._finalized.append(t)
            else:
                keep.append(t)
        self._tracks = keep

    def flush(self) -> None:
        self._finalized.extend(self._tracks)
        self._tracks = []

    def events(self) -> List[SurveyEvent]:
        events: List[SurveyEvent] = []
        for i, t in enumerate(self._finalized):
            if t.hits < self.min_persist:
                continue
            snr = 10.0 * np.log10(t.peak_power / max(t.noise_power, 1e-20))
            span = max(t.last_frame - t.first_frame + 1, 1)
            events.append(SurveyEvent(
                event_id=f"evc_{i:06d}",
                center_hz=t.center_hz,
                bw_hz=t.bw_hz,
                t_start_s=t.first_frame * self.frame_period_s,
                t_end_s=(t.last_frame + 1) * self.frame_period_s,
                kind="continuous",
                snr_db=float(snr),
                peak_power_db=float(10.0 * np.log10(max(t.peak_power, 1e-20))),
                hits=t.hits,
                duty_cycle=float(t.hits) / float(span),
            ))
        return events
