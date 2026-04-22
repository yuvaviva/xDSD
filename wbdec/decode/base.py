"""Decoder interface + result dataclasses.

Every adapter consumes the SigMF channel produced by stage 3 and emits
decoded audio (optional) + a JSON-lines frame stream. Adapters are stateless
enough to be picklable for ``concurrent.futures.ProcessPoolExecutor``; any
per-run configuration lives in ``DecodeOptions``.
"""

from __future__ import annotations

import abc
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DecodeOptions:
    """Run-scoped options passed from the CLI / config into every adapter."""
    out_dir: str                       # root output directory (absolute)
    dsd_fme_binary: str = "dsd-fme"
    tetra_rx_binary: str = "tetra-rx"
    use_gr_dsd: bool = False           # try the gr-dsd in-process adapter
    timeout_s: float = 120.0
    extra_args: List[str] = field(default_factory=list)


@dataclass
class FrameRecord:
    """One entry written to ``frames.jsonl``. Deliberately permissive — each
    adapter emits the fields it recovers; the analyzer (M4) is the single
    consumer that has to know how to interpret them.
    """
    t_offset_s: float
    type: str                          # e.g. "P25_HDU", "DMR_VOICE", "TETRA_MAC"
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_json_line(self) -> str:
        record = {"t_offset_s": self.t_offset_s, "type": self.type}
        record.update(self.extras)
        return json.dumps(record, default=_json_default)


@dataclass
class DecodeResult:
    """Returned by every adapter (always — never raises)."""
    event_id: str
    protocol: str                      # classified label, e.g. "p25_c4fm"
    adapter: str                       # adapter name
    ok: bool
    pcm_wav_path: Optional[str] = None
    frames_jsonl_path: Optional[str] = None
    # Extracted metadata (populated by the adapter's log parser):
    nac: Optional[int] = None
    algid: Optional[int] = None
    keyid: Optional[int] = None
    duration_s: float = 0.0
    n_frames: int = 0
    error: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _json_default(o):
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(f"not serializable: {type(o).__name__}")


# ---------------------------------------------------------------------------
# Adapter ABC
# ---------------------------------------------------------------------------

class ProtocolAdapter(abc.ABC):
    """Base class for all decoder adapters.

    Subclasses must set ``name`` (adapter identifier, unique across the
    registry), ``protocols`` (list of wbdec labels this adapter can handle,
    in preference order), and ``demod_hint`` ("fm" or "linear") which must
    match the channel's own demod_hint for the adapter to be selected.
    """

    name: str = "base"
    protocols: tuple[str, ...] = ()
    demod_hint: str = "fm"

    @abc.abstractmethod
    def is_available(self) -> bool:
        """True iff this adapter can run on the current machine."""

    @abc.abstractmethod
    def decode(self, channel_meta_path: str, opts: DecodeOptions
               ) -> DecodeResult:
        """Decode a single channel. Must not raise — return a
        ``DecodeResult`` with ``ok=False`` and a populated ``error`` instead.
        """

    # Convenience helpers shared across adapters:
    @staticmethod
    def load_channel_meta(meta_path: str) -> Dict[str, Any]:
        with open(meta_path, "r") as fh:
            return json.load(fh)

    @staticmethod
    def channel_data_path(meta_path: str) -> str:
        if meta_path.endswith(".sigmf-meta"):
            return meta_path[:-len(".sigmf-meta")] + ".sigmf-data"
        return os.path.splitext(meta_path)[0] + ".sigmf-data"
