"""Extended M3U playlist generator for decoded call WAVs."""

from __future__ import annotations

import os

from .report import Report


def _nice_label(channel) -> str:
    parts = [
        f"{channel.center_hz/1e6:10.4f} MHz",
        (channel.label or "?"),
        f"{channel.t_start_s:6.2f}s",
    ]
    if channel.encryption.encrypted:
        alg = channel.encryption.algorithm or "ENCRYPTED"
        parts.append(f"[{alg}]")
    return "  ".join(parts)


def render_m3u(report: Report) -> str:
    lines = ["#EXTM3U"]
    for c in report.channels:
        if not c.decoded_ok or not c.wav_path:
            continue
        rel = os.path.relpath(c.wav_path, report.out_dir)
        lines.append(f"#EXTINF:-1,{_nice_label(c)}")
        # Forward slashes survive both posix and windows media players.
        lines.append(rel.replace(os.sep, "/"))
    return "\n".join(lines) + "\n"
