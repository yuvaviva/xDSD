"""End-to-end pipeline runner: survey → channelize → decode → analyze.

Stage 1 (capture/ingest) is implicit — `run_survey` opens the SplitSet
on its own. The pipeline is a thin orchestrator with a single responsibility:
run the four stages in order, fail loud on any error, and return the final
``Report``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from ..analyze.report import Report
from ..analyze.run import run_analyze
from ..channelize.run import run_channelize
from ..config import Config
from ..decode.run import run_decode
from ..survey.run import run_survey


@dataclass
class PipelineResult:
    survey_events: int
    channels: int
    decoded_ok: int
    encrypted: int
    trunking_events: int
    out_dir: str
    report: Report


def run_pipeline(cfg: Config, out_dir: Optional[str] = None) -> PipelineResult:
    """Run all four stages back-to-back. Returns aggregated counters."""
    if out_dir:
        cfg.out_dir = out_dir
    os.makedirs(cfg.out_dir, exist_ok=True)

    survey = run_survey(cfg)
    run_channelize(cfg)
    run_decode(cfg)
    report = run_analyze(cfg)

    return PipelineResult(
        survey_events=len(survey.events),
        channels=report.num_channels,
        decoded_ok=report.num_decoded,
        encrypted=report.num_encrypted,
        trunking_events=len(getattr(report, "trunking_events", []) or []),
        out_dir=cfg.out_dir,
        report=report,
    )
