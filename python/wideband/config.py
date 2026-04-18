"""Configuration dataclasses and YAML loader for the wideband pipeline."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


@dataclass
class IngestConfig:
    folder: str
    sample_rate: float = 10_000_000.0
    center_hz: float = 0.0
    format: Optional[str] = None  # "hackrf_int8" | "rtl_uint8" | "gqrx_fc32" | "sigmf" | "wav" | None=auto
    block_size: int = 1 << 20


@dataclass
class DetectConfig:
    nperseg: int = 8192
    nav: int = 32                 # number of Welch segments averaged per frame
    cfar_guard: int = 4
    cfar_train: int = 32
    cfar_pfa: float = 1e-4
    min_bw_hz: float = 5_000.0
    max_bw_hz: float = 40_000.0
    min_persist_frames: int = 2
    max_absent_frames: int = 2


@dataclass
class ClassifyConfig:
    snippet_samples: int = 1 << 15
    confidence_threshold: float = 0.55


@dataclass
class DecodeConfig:
    enable_p25: bool = True
    enable_dmr: bool = True
    enable_nxdn: bool = True
    enable_dstar: bool = True
    enable_tetra: bool = False     # requires osmocom-tetra tetra-rx
    tetra_rx_binary: str = "tetra-rx"
    enable_dpmr: bool = False      # detection only; decode unsupported
    workers: int = 2
    # Backend selection for the DSD-family decoder. "gr" uses the in-tree
    # gr-dsd GNU Radio block (requires successful C++ build). "subprocess"
    # shells out to an external DSD CLI (DSD+, DSDcc, dsd-fme, szechyjs/dsd)
    # — the practical choice on Windows / radioconda GR 3.10 where the
    # gr-dsd C++ block cannot be built.
    dsd_backend: str = "gr"
    dsd_binary: str = "dsd-fme"
    dsd_flavor: str = "dsd_fme"
    dsd_extra_args: List[str] = field(default_factory=list)


@dataclass
class AttackToggles:
    p25_adp: bool = False
    p25_des_known_key: bool = False
    p25_des_key_hex: Optional[str] = None
    dmr_bp: bool = False
    tetra_tea1: bool = False
    iv_reuse: bool = True
    max_cpu_seconds_per_event: float = 30.0


@dataclass
class CryptoConfig:
    detect: bool = True
    enable_key_recovery: bool = False
    attacks: AttackToggles = field(default_factory=AttackToggles)


@dataclass
class OutputConfig:
    out_dir: str = "wideband_out"
    write_wav: bool = True
    write_baseband_sigmf: bool = False
    write_spectrogram_png: bool = True


@dataclass
class WidebandConfig:
    ingest: IngestConfig
    detect: DetectConfig = field(default_factory=DetectConfig)
    classify: ClassifyConfig = field(default_factory=ClassifyConfig)
    decode: DecodeConfig = field(default_factory=DecodeConfig)
    crypto: CryptoConfig = field(default_factory=CryptoConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def _merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def load_config(path: str) -> WidebandConfig:
    """Load WidebandConfig from a YAML or JSON file.

    YAML is preferred but only required if the file has a .yaml/.yml extension.
    JSON is always supported so the package remains usable without PyYAML.
    """
    with open(path, "r") as fh:
        raw = fh.read()
    ext = os.path.splitext(path)[1].lower()
    if ext in (".yaml", ".yml"):
        import yaml  # type: ignore
        data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)
    return _from_dict(data)


def _from_dict(data: Dict[str, Any]) -> WidebandConfig:
    ing = IngestConfig(**data["ingest"])
    det = DetectConfig(**data.get("detect", {}))
    cls = ClassifyConfig(**data.get("classify", {}))
    dec = DecodeConfig(**data.get("decode", {}))
    crypto_raw = dict(data.get("crypto", {}))
    attacks_raw = crypto_raw.pop("attacks", {}) or {}
    crypto = CryptoConfig(attacks=AttackToggles(**attacks_raw), **crypto_raw)
    out = OutputConfig(**data.get("output", {}))
    return WidebandConfig(ingest=ing, detect=det, classify=cls,
                          decode=dec, crypto=crypto, output=out)
