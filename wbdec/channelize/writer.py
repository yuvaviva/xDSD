"""SigMF writer for per-channel baseband.

Writes interleaved cf32_le as the sample stream grows, then emits the
``.sigmf-meta`` at close time with final sample count + source annotations.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np


@dataclass
class ChannelMetaInputs:
    event_id: str
    label: Optional[str]
    label_confidence: float
    source_capture_meta: str
    source_center_hz: float
    source_sample_rate_hz: float
    channel_center_hz: float       # absolute RF
    channel_bw_hz: float
    out_sample_rate_hz: float
    t_start_s: float
    t_end_s: float
    demod_hint: str
    apply_rrc: bool


class SigMFChannelWriter:
    def __init__(self, out_dir: str, event_id: str, meta_inputs: ChannelMetaInputs):
        os.makedirs(out_dir, exist_ok=True)
        self.meta_inputs = meta_inputs
        self.data_path = os.path.join(out_dir, f"{event_id}.sigmf-data")
        self.meta_path = os.path.join(out_dir, f"{event_id}.sigmf-meta")
        self._fh = open(self.data_path, "wb")
        self._count = 0

    def write(self, samples: np.ndarray) -> None:
        if samples.dtype != np.complex64:
            samples = samples.astype(np.complex64)
        # cf32_le: interleaved float32 I, Q.
        buf = np.empty(samples.size * 2, dtype="<f4")
        buf[0::2] = samples.real
        buf[1::2] = samples.imag
        self._fh.write(buf.tobytes())
        self._count += samples.size

    def close(self) -> Dict[str, Any]:
        self._fh.flush()
        self._fh.close()
        mi = self.meta_inputs
        meta = {
            "global": {
                "core:datatype":    "cf32_le",
                "core:sample_rate": mi.out_sample_rate_hz,
                "core:version":     "1.0.0",
                "core:author":      "wbdec",
                "core:description": f"channel {mi.event_id} extracted by wbdec",
                "wbdec:event_id":        mi.event_id,
                "wbdec:label":           mi.label,
                "wbdec:label_confidence": mi.label_confidence,
                "wbdec:source_capture_meta": os.path.abspath(mi.source_capture_meta),
                "wbdec:source_center_hz":    mi.source_center_hz,
                "wbdec:source_sample_rate_hz": mi.source_sample_rate_hz,
                "wbdec:channel_bw_hz":   mi.channel_bw_hz,
                "wbdec:demod_hint":      mi.demod_hint,
                "wbdec:rrc_applied":     mi.apply_rrc,
                "wbdec:samples":         self._count,
            },
            "captures": [{
                "core:sample_start": 0,
                "core:frequency":    mi.channel_center_hz,
                "wbdec:t_start_s":   mi.t_start_s,
                "wbdec:t_end_s":     mi.t_end_s,
            }],
            "annotations": [],
        }
        with open(self.meta_path, "w") as fh:
            json.dump(meta, fh, indent=2)
        return meta

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if not self._fh.closed:
            self.close()
