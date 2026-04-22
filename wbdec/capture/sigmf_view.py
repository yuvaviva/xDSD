"""Virtual SigMF view over a SplitSet.

Writes a ``capture.sigmf-meta`` that describes the stitched stream. The
``core:sample_start`` / ``core:datetime`` annotations carry split boundaries
so downstream tools can map absolute sample indices back to the source file.

Does NOT copy any sample data — the view points at the original split files.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List

from .splits import SplitSet


_DATATYPE_FROM_FORMAT = {
    "hackrf_int8": "cs8_le",
    "rtl_uint8":   "cu8_le",
    "gqrx_fc32":   "cf32_le",
    "sigmf":       "cf32_le",   # abstract; canonical form after conversion
    "wav":         "cf32_le",
}


@dataclass
class VirtualSigMF:
    split_set: SplitSet
    meta: Dict[str, Any]

    @classmethod
    def from_split_set(cls, split_set: SplitSet,
                       datetime_utc: str | None = None) -> "VirtualSigMF":
        dt = datetime_utc or _dt.datetime.now(_dt.timezone.utc).isoformat()
        datatype = _DATATYPE_FROM_FORMAT.get(split_set.fmt, "cf32_le")

        captures: List[Dict[str, Any]] = []
        sample_offset = 0
        from .readers import FORMATS
        reader_cls = FORMATS[split_set.fmt]
        bps = getattr(reader_cls, "bytes_per_sample", 2)
        for path in split_set.files:
            nb = os.path.getsize(path)
            captures.append({
                "core:sample_start": sample_offset,
                "core:frequency":    split_set.center_hz,
                "core:datetime":     dt,
                "wbdec:source_file": os.path.abspath(path),
                "wbdec:source_bytes": nb,
            })
            sample_offset += nb // max(bps, 1)

        meta = {
            "global": {
                "core:datatype":    datatype,
                "core:sample_rate": split_set.sample_rate_hz,
                "core:version":     "1.0.0",
                "core:author":      "wbdec",
                "core:description": "virtual SigMF view over split SDR capture",
                "wbdec:folder":     os.path.abspath(split_set.folder),
                "wbdec:source_format": split_set.fmt,
                "wbdec:total_samples": sample_offset,
                "wbdec:duration_s":  sample_offset / max(split_set.sample_rate_hz, 1.0),
            },
            "captures":    captures,
            "annotations": [
                {
                    "core:sample_start": g_ofs,
                    "core:sample_count": g.dropped_samples,
                    "core:comment":      f"gap after {g.after_file}",
                }
                for g_ofs, g in _gap_offsets(split_set)
            ],
        }
        return cls(split_set=split_set, meta=meta)


def _gap_offsets(split_set: SplitSet):
    # We can only report gaps AFTER the split set has been iterated through;
    # before that, split_set.gaps is empty. The viewer annotations therefore
    # reflect only previously-recorded gaps. Return an iterator of
    # (offset, gap) — offset is 0 for now (to be filled by the survey stage).
    for g in split_set.gaps:
        yield 0, g


def write_view_meta(view: VirtualSigMF, out_dir: str,
                    basename: str = "capture") -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{basename}.sigmf-meta")
    with open(path, "w") as fh:
        json.dump(view.meta, fh, indent=2)
    return path
