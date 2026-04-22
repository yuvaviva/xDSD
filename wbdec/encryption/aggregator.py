"""Protocol-aware dispatcher: picks the right probe based on channel label."""

from __future__ import annotations

import json
import os
from typing import Iterable, List

from .dmr import probe_dmr_frames
from .p25 import probe_p25_frames
from .schema import EncryptionFinding
from .tetra import probe_tetra_frames


_PROTO_PROBE = {
    "p25_c4fm": probe_p25_frames,
    "dmr":      probe_dmr_frames,
    "dpmr":     probe_dmr_frames,   # similar scrambler-class encryption surface
    "tetra":    probe_tetra_frames,
}


def probe_frames(label: str | None, frames: Iterable[dict]) -> EncryptionFinding:
    if not label or label not in _PROTO_PROBE:
        return EncryptionFinding(
            encrypted=False,
            evidence=[f"no encryption probe for label '{label}'"] if label
                     else ["label missing — cannot probe"],
        )
    return _PROTO_PROBE[label](frames)


def load_frames_jsonl(path: str) -> List[dict]:
    if not path or not os.path.exists(path):
        return []
    out: List[dict] = []
    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
