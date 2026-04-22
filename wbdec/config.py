"""Configuration model for wbdec.

Uses plain dataclasses so the package is importable without pydantic at runtime
(pydantic would be nice for validation but is not required for M1). A small
``load_config`` accepts YAML or JSON.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# capture
# ---------------------------------------------------------------------------

@dataclass
class CaptureConfig:
    folder: str
    sample_rate_hz: float = 10_000_000.0
    center_hz: float = 0.0
    format: Optional[str] = None         # "hackrf_int8" | "rtl_uint8" | "gqrx_fc32" | "sigmf" | "wav"
    chunk_samples: int = 1 << 20          # ~1 Msample chunks (~8 MB cf32)


# ---------------------------------------------------------------------------
# survey
# ---------------------------------------------------------------------------

@dataclass
class SurveyConfig:
    nperseg: int = 8192
    welch_overlap: float = 0.5
    frame_samples: int = 1 << 20          # samples per time-bin; 2^20 @ 10 Msps ≈ 105 ms
    cfar_guard: int = 4
    cfar_train: int = 32
    cfar_pfa: float = 1e-4
    min_bw_hz: float = 5_000.0
    max_bw_hz: float = 50_000.0
    # Continuous-tracker thresholds:
    min_persist_frames: int = 2
    max_absent_frames: int = 3
    # Burst-tracker thresholds (DMR ~30 ms slots, TETRA ~14 ms frames):
    burst_min_duty_cycle: float = 0.15    # fraction of frames present within a window
    burst_window_frames: int = 8
    merge_freq_tol_hz: float = 6_250.0    # merge detections within this band


# ---------------------------------------------------------------------------
# channelize, decode, encryption (stubs for M1; filled in M2+)
# ---------------------------------------------------------------------------

@dataclass
class ChannelizeConfig:
    grid_hz: float = 12_500.0             # default channel spacing
    out_dir: str = "channels"


@dataclass
class DecodeConfig:
    out_dir: str = "calls"
    dsd_fme_binary: str = "dsd-fme"
    tetra_rx_binary: str = "tetra-rx"
    use_gr_dsd: bool = False              # try the in-process adapter too
    workers: int = 2


@dataclass
class AnalyzeConfig:
    out_dir: str = "report"
    write_html: bool = True


@dataclass
class Config:
    capture: CaptureConfig
    survey: SurveyConfig = field(default_factory=SurveyConfig)
    channelize: ChannelizeConfig = field(default_factory=ChannelizeConfig)
    decode: DecodeConfig = field(default_factory=DecodeConfig)
    analyze: AnalyzeConfig = field(default_factory=AnalyzeConfig)
    out_dir: str = "wbdec_out"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _from_dict(data: Dict[str, Any]) -> Config:
    capture = CaptureConfig(**data["capture"])
    survey = SurveyConfig(**data.get("survey", {}))
    channelize = ChannelizeConfig(**data.get("channelize", {}))
    decode = DecodeConfig(**data.get("decode", {}))
    analyze = AnalyzeConfig(**data.get("analyze", {}))
    return Config(
        capture=capture, survey=survey, channelize=channelize,
        decode=decode, analyze=analyze,
        out_dir=data.get("out_dir", "wbdec_out"),
    )


def load_config(path: str) -> Config:
    with open(path, "r") as fh:
        raw = fh.read()
    ext = os.path.splitext(path)[1].lower()
    if ext in (".yaml", ".yml"):
        import yaml  # type: ignore
        data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)
    return _from_dict(data)
