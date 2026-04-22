"""Burst tracker for TDMA signals (DMR slots, TETRA frames).

Reduces jitter between transmissions by looking at a rolling window of
frames and keeping a track alive while duty-cycle stays above a threshold.
A channel that shows up in 2/8 frames over a sliding window is emitted as
one ``burst`` event rather than two separate ``continuous`` events with a
big absence gap.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Tuple

import numpy as np

from .schema import SurveyEvent


@dataclass
class _BurstTrack:
    center_hz: float
    bw_hz: float
    first_frame: int
    last_seen_frame: int
    hits: int = 0
    total_frames: int = 0
    peak_power: float = 0.0
    noise_power: float = 1e-20
    recent_hits: Deque[int] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.recent_hits is None:
            self.recent_hits = deque()


class BurstTracker:
    """Maintains tracks keyed by quantised frequency bin.

    Quantisation is to the merge-tolerance grid so DMR slots at the same
    nominal carrier land in the same bin regardless of small estimation noise.
    """

    def __init__(self, frame_period_s: float, window_frames: int,
                 min_duty_cycle: float, merge_tol_hz: float,
                 min_bursts: int = 2):
        self.frame_period_s = frame_period_s
        self.window = window_frames
        self.min_duty = min_duty_cycle
        self.merge_tol = merge_tol_hz
        self.min_bursts = min_bursts
        self._tracks: Dict[int, _BurstTrack] = {}
        self._finalized: List[_BurstTrack] = []

    def _bin(self, center_hz: float) -> int:
        return int(round(center_hz / self.merge_tol))

    def update(self, frame_idx: int,
               detections: List[Tuple[float, float, float, float]]) -> None:
        seen_bins: set[int] = set()
        for center, bw, pk, noise in detections:
            key = self._bin(center)
            seen_bins.add(key)
            t = self._tracks.get(key)
            if t is None:
                t = _BurstTrack(
                    center_hz=center, bw_hz=bw,
                    first_frame=frame_idx, last_seen_frame=frame_idx,
                    peak_power=pk, noise_power=max(noise, 1e-20),
                )
                self._tracks[key] = t
            t.center_hz = 0.85 * t.center_hz + 0.15 * center
            t.bw_hz = max(t.bw_hz, bw)
            t.last_seen_frame = frame_idx
            t.hits += 1
            t.peak_power = max(t.peak_power, pk)
            t.noise_power = 0.8 * t.noise_power + 0.2 * max(noise, 1e-20)
            t.recent_hits.append(frame_idx)

        # Purge stale tracks and update recent-hit windows.
        lo = frame_idx - self.window + 1
        to_drop: List[int] = []
        for key, t in self._tracks.items():
            while t.recent_hits and t.recent_hits[0] < lo:
                t.recent_hits.popleft()
            duty = len(t.recent_hits) / float(self.window)
            # Track is "alive" as long as it has any hit in window OR hit us
            # this frame.
            if not t.recent_hits and key not in seen_bins:
                # truly gone
                t.total_frames = t.last_seen_frame - t.first_frame + 1
                self._finalized.append(t)
                to_drop.append(key)
            else:
                t.total_frames = frame_idx - t.first_frame + 1
                # note: duty is informational here; events() applies threshold
                _ = duty
        for k in to_drop:
            del self._tracks[k]

    def flush(self) -> None:
        for t in self._tracks.values():
            t.total_frames = max(t.last_seen_frame - t.first_frame + 1, 1)
            self._finalized.append(t)
        self._tracks.clear()

    def events(self) -> List[SurveyEvent]:
        out: List[SurveyEvent] = []
        for i, t in enumerate(self._finalized):
            span = max(t.total_frames, 1)
            duty = t.hits / float(span)
            if t.hits < self.min_bursts:
                continue
            if duty < self.min_duty:
                continue
            # Very-high-duty tracks belong to the continuous tracker, not here.
            if duty > 0.95:
                continue
            snr = 10.0 * np.log10(t.peak_power / max(t.noise_power, 1e-20))
            out.append(SurveyEvent(
                event_id=f"evb_{i:06d}",
                center_hz=t.center_hz,
                bw_hz=t.bw_hz,
                t_start_s=t.first_frame * self.frame_period_s,
                t_end_s=(t.last_seen_frame + 1) * self.frame_period_s,
                kind="burst",
                snr_db=float(snr),
                peak_power_db=float(10.0 * np.log10(max(t.peak_power, 1e-20))),
                hits=t.hits,
                duty_cycle=float(duty),
            ))
        return out
