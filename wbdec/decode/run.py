"""Stage-4 entry point: run the right adapter for every channel."""

from __future__ import annotations

import glob
import json
import os
from dataclasses import asdict
from typing import Dict, List, Optional

from ..config import Config
from ..orchestrate.pool import run_pool
from .base import DecodeOptions, DecodeResult
from .registry import all_adapters, get_adapter_by_name, get_adapters_for


def _load_channel_meta(path: str) -> dict:
    with open(path, "r") as fh:
        return json.load(fh)


def _select_adapter(label: str | None, demod_hint: str | None,
                    use_gr_dsd: bool) -> Optional[str]:
    """Return the name of the adapter to use for this channel, or None."""
    if not label:
        return None
    candidates = get_adapters_for(label, demod_hint=demod_hint)
    if not candidates:
        return None
    # Deterministic order: gr_dsd (only if enabled), then dsd_fme, then others.
    ordered: List[type] = []
    for cls in candidates:
        if cls.name == "gr_dsd" and not use_gr_dsd:
            continue
        ordered.append(cls)
    if not ordered:
        return None
    # Simple ranking per demod_hint + preference.
    pref = {
        "fm":     ["dsd_fme", "gr_dsd"],
        "linear": ["tetra_rx", "tetra_native"],
    }.get(demod_hint or "fm", [])
    ordered.sort(key=lambda cls: pref.index(cls.name) if cls.name in pref else 999)
    return ordered[0].name


def _decode_one(payload: dict) -> dict:
    """Worker entry — picklable. Reconstructs the adapter from name."""
    meta_path = payload["meta_path"]
    adapter_name = payload["adapter_name"]
    opts = DecodeOptions(**payload["opts"])
    cls = get_adapter_by_name(adapter_name)
    if cls is None:
        return DecodeResult(
            event_id=os.path.splitext(os.path.basename(meta_path))[0],
            protocol="unknown", adapter=adapter_name, ok=False,
            error=f"adapter not found: {adapter_name}",
        ).to_dict()
    try:
        result = cls().decode(meta_path, opts)
    except Exception as exc:  # belt-and-braces; adapters aren't supposed to raise
        return DecodeResult(
            event_id=os.path.splitext(os.path.basename(meta_path))[0],
            protocol="unknown", adapter=adapter_name, ok=False,
            error=f"adapter raised: {exc}",
        ).to_dict()
    return result.to_dict()


def run_decode(cfg: Config, out_dir: Optional[str] = None,
               channels_dir: Optional[str] = None,
               workers: Optional[int] = None) -> Dict[str, dict]:
    """Stage 4. Returns ``{event_id: decode_result_dict}`` and writes
    ``decode.json`` to ``out_dir``.
    """
    out_dir = out_dir or cfg.out_dir
    channels_dir = channels_dir or os.path.join(out_dir, cfg.channelize.out_dir)
    calls_dir = os.path.join(out_dir, cfg.decode.out_dir)
    frames_dir = os.path.join(out_dir, "frames")
    os.makedirs(calls_dir, exist_ok=True)
    os.makedirs(frames_dir, exist_ok=True)

    metas = sorted(glob.glob(os.path.join(channels_dir, "*.sigmf-meta")))
    if not metas:
        raise FileNotFoundError(
            f"no channel meta files in {channels_dir} — run `wbdec channelize` first")

    opts = DecodeOptions(
        out_dir=os.path.abspath(out_dir),
        dsd_fme_binary=cfg.decode.dsd_fme_binary,
        tetra_rx_binary=cfg.decode.tetra_rx_binary,
        use_gr_dsd=cfg.decode.use_gr_dsd,
        extra_args=[],
    )
    opts_dict = asdict(opts)

    payloads = []
    skipped: List[Dict] = []
    for meta_path in metas:
        meta = _load_channel_meta(meta_path)
        g = meta["global"]
        label = g.get("wbdec:label")
        hint = g.get("wbdec:demod_hint", "fm")
        adapter_name = _select_adapter(label, hint, cfg.decode.use_gr_dsd)
        eid = g.get("wbdec:event_id") or os.path.splitext(os.path.basename(meta_path))[0]
        if adapter_name is None:
            skipped.append({
                "event_id": eid, "label": label, "reason": "no adapter registered",
            })
            continue
        payloads.append({
            "meta_path": meta_path,
            "adapter_name": adapter_name,
            "opts": opts_dict,
        })

    results: Dict[str, dict] = {}
    # Use workers from the function arg, then config, then 2.
    w = workers if workers is not None else max(1, cfg.decode.workers)
    # In-process shortcut when workers=1 — makes debugging + tests painless.
    if w <= 1 or len(payloads) <= 1:
        for p in payloads:
            r = _decode_one(p)
            results[r["event_id"]] = r
    else:
        for r in run_pool(_decode_one, payloads, workers=w):
            if isinstance(r, Exception):
                continue
            results[r["event_id"]] = r

    summary = {
        "num_channels": len(metas),
        "num_decoded":  sum(1 for r in results.values() if r["ok"]),
        "num_skipped":  len(skipped),
        "results":      results,
        "skipped":      skipped,
    }
    with open(os.path.join(out_dir, "decode.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    return summary
