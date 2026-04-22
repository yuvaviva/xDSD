"""Data structures + aggregator for the analyze stage.

Pulls together four on-disk artifacts into one ``Report``:

    survey.json             (freq/time/labels/SNR)
    decode.json             (per-channel decode result + adapter)
    channels/*.sigmf-meta   (per-channel metadata)
    frames/*.jsonl          (per-channel frame streams)

The output schema is stable across adapters — the analyzer is the single
consumer of adapter-specific fields.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from ..encryption.aggregator import load_frames_jsonl, probe_frames
from ..encryption.schema import EncryptionFinding


@dataclass
class ChannelReport:
    event_id: str
    label: Optional[str]
    label_confidence: float
    kind: str                        # "continuous" | "burst"
    center_hz: float
    bw_hz: float
    snr_db: float
    t_start_s: float
    t_end_s: float
    duration_s: float

    adapter: Optional[str]
    decoded_ok: bool
    wav_path: Optional[str]
    frames_jsonl_path: Optional[str]
    decode_error: Optional[str]

    frame_counts: Dict[str, int]
    nac: Optional[int]

    encryption: EncryptionFinding

    # Trunking annotations (filled in by the trunking annotator post-aggregate;
    # default to None when no trunking signalling was observed).
    talkgroup_id: Optional[int] = None
    source_id: Optional[int] = None
    granted_by_event_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["encryption"] = self.encryption.to_dict()
        return d


@dataclass
class Report:
    out_dir: str
    capture_meta_path: Optional[str]
    sample_rate_hz: float
    center_hz: float
    duration_s: float
    num_channels: int
    num_decoded: int
    num_encrypted: int
    channels: List[ChannelReport] = field(default_factory=list)
    # Populated by the trunking annotator after aggregate(); defaults to [].
    trunking_events: List[Any] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "out_dir":           self.out_dir,
            "capture_meta_path": self.capture_meta_path,
            "sample_rate_hz":    self.sample_rate_hz,
            "center_hz":         self.center_hz,
            "duration_s":        self.duration_s,
            "num_channels":      self.num_channels,
            "num_decoded":       self.num_decoded,
            "num_encrypted":     self.num_encrypted,
            "channels":          [c.to_dict() for c in self.channels],
            "trunking_events":   [
                e.to_dict() if hasattr(e, "to_dict") else e
                for e in (self.trunking_events or [])
            ],
        }


def _read_json(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, "r") as fh:
        return json.load(fh)


def aggregate(out_dir: str) -> Report:
    """Read the stage 1-4 artifacts in ``out_dir`` and build a ``Report``."""
    survey = _read_json(os.path.join(out_dir, "survey.json")) or {}
    decode = _read_json(os.path.join(out_dir, "decode.json")) or {}
    events_by_id: Dict[str, dict] = {
        e["event_id"]: e for e in survey.get("events", [])
    }
    results_by_id: Dict[str, dict] = decode.get("results", {})

    # We use the channel meta files as the authoritative per-channel directory,
    # falling back to survey events when decode was skipped.
    channels_dir = os.path.join(out_dir, "channels")
    meta_paths: List[str] = []
    if os.path.isdir(channels_dir):
        for name in sorted(os.listdir(channels_dir)):
            if name.endswith(".sigmf-meta"):
                meta_paths.append(os.path.join(channels_dir, name))

    channels: List[ChannelReport] = []
    for meta_path in meta_paths:
        meta = _read_json(meta_path) or {}
        g = meta.get("global", {})
        ev_id = g.get("wbdec:event_id") or os.path.splitext(
            os.path.basename(meta_path))[0]
        survey_ev = events_by_id.get(ev_id, {})
        decode_r = results_by_id.get(ev_id, {})

        frames_path = decode_r.get("frames_jsonl_path")
        frames = load_frames_jsonl(frames_path) if frames_path else []
        frame_counts: Counter[str] = Counter(fr.get("type", "unknown") for fr in frames)

        finding = probe_frames(g.get("wbdec:label") or survey_ev.get("label"),
                               frames)

        cap = (meta.get("captures") or [{}])[0]
        center = float(cap.get("core:frequency", survey_ev.get("center_hz", 0.0)))
        t_start = float(cap.get("wbdec:t_start_s",
                                survey_ev.get("t_start_s", 0.0)))
        t_end = float(cap.get("wbdec:t_end_s",
                              survey_ev.get("t_end_s", 0.0)))

        channels.append(ChannelReport(
            event_id=ev_id,
            label=g.get("wbdec:label") or survey_ev.get("label"),
            label_confidence=float(g.get("wbdec:label_confidence",
                                         survey_ev.get("label_confidence", 0.0))),
            kind=survey_ev.get("kind", "continuous"),
            center_hz=center,
            bw_hz=float(g.get("wbdec:channel_bw_hz",
                              survey_ev.get("bw_hz", 0.0))),
            snr_db=float(survey_ev.get("snr_db", 0.0)),
            t_start_s=t_start,
            t_end_s=t_end,
            duration_s=float(decode_r.get("duration_s",
                                          max(0.0, t_end - t_start))),
            adapter=decode_r.get("adapter"),
            decoded_ok=bool(decode_r.get("ok", False)),
            wav_path=decode_r.get("pcm_wav_path"),
            frames_jsonl_path=frames_path,
            decode_error=decode_r.get("error"),
            frame_counts=dict(frame_counts),
            nac=decode_r.get("nac"),
            encryption=finding,
        ))

    return Report(
        out_dir=os.path.abspath(out_dir),
        capture_meta_path=survey.get("capture_meta_path"),
        sample_rate_hz=float(survey.get("sample_rate_hz", 0.0)),
        center_hz=float(survey.get("center_hz", 0.0)),
        duration_s=float(survey.get("duration_s", 0.0)),
        num_channels=len(channels),
        num_decoded=sum(1 for c in channels if c.decoded_ok),
        num_encrypted=sum(1 for c in channels if c.encryption.encrypted),
        channels=channels,
    )
