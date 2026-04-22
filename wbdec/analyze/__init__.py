"""Analyze stage: aggregate stages 1-4 into a single human-readable report."""

from .report import ChannelReport, Report, aggregate
from .html_report import render_html
from .m3u import render_m3u
from .run import run_analyze

__all__ = [
    "ChannelReport", "Report", "aggregate",
    "render_html", "render_m3u", "run_analyze",
]
