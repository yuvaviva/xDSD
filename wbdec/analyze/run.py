"""Stage-5 entry point: ingest all prior-stage artifacts → report.{json,html} + m3u."""

from __future__ import annotations

import json
import os
from typing import Optional

from ..config import Config
from .html_report import render_html
from .m3u import render_m3u
from .report import Report, aggregate


def run_analyze(cfg: Config, out_dir: Optional[str] = None) -> Report:
    out_dir = out_dir or cfg.out_dir
    report = aggregate(out_dir)

    # Trunking annotation: enrich channels + attach event list.
    from ..trunking.annotator import attach_to_report
    attach_to_report(report)

    # JSON — full structured dump.
    with open(os.path.join(out_dir, "report.json"), "w") as fh:
        json.dump(report.to_dict(), fh, indent=2, default=_json_default)

    # HTML — single-file, browser-openable.
    if cfg.analyze.write_html:
        with open(os.path.join(out_dir, "report.html"), "w", encoding="utf-8") as fh:
            fh.write(render_html(report))

    # Playlist of decoded calls.
    calls_dir = os.path.join(out_dir, cfg.decode.out_dir)
    os.makedirs(calls_dir, exist_ok=True)
    with open(os.path.join(calls_dir, "index.m3u"), "w", encoding="utf-8") as fh:
        fh.write(render_m3u(report))
    return report


def _json_default(o):
    if hasattr(o, "item"):
        return o.item()
    if hasattr(o, "__dict__"):
        return o.__dict__
    raise TypeError(f"not serializable: {type(o).__name__}")
