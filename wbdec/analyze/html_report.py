"""Single-file HTML report generator.

Inline CSS, no JavaScript framework, no Jinja. Embeds the PSD as a
relative image link (already on disk); audio as standard HTML5
<audio controls src="...">. The result opens in a browser from the
``wbdec_out/`` directory with no further setup.
"""

from __future__ import annotations

import html
import os
from datetime import datetime, timezone
from typing import Iterable

from .report import ChannelReport, Report


_CSS = """
  body { font-family: -apple-system, Segoe UI, sans-serif; margin: 2em auto;
         max-width: 1100px; color: #222; line-height: 1.4; }
  h1 { margin-bottom: 0.2em; }
  .meta { color: #666; margin-bottom: 1em; }
  .stats { display: flex; gap: 1.5em; margin: 1em 0; }
  .stat { background: #f5f5f7; padding: 0.6em 1em; border-radius: 6px; min-width: 110px; }
  .stat .k { font-size: 0.85em; color: #666; text-transform: uppercase;
             letter-spacing: 0.05em; }
  .stat .v { font-size: 1.4em; font-weight: 600; }
  table { width: 100%; border-collapse: collapse; margin-top: 1em;
          font-size: 0.92em; }
  th, td { padding: 6px 8px; text-align: left; border-bottom: 1px solid #eee;
           vertical-align: top; }
  th { background: #f5f5f7; position: sticky; top: 0; }
  tr.enc td { background: #fff6f6; }
  tr.failed td { color: #888; }
  .badge { display: inline-block; padding: 1px 7px; border-radius: 4px;
           font-size: 0.8em; font-weight: 600; }
  .badge.ok { background: #e2f7e4; color: #1a7a2e; }
  .badge.enc { background: #fde0e0; color: #a11; }
  .badge.fail { background: #eee; color: #555; }
  .evidence { color: #666; font-size: 0.85em; }
  code { background: #f2f2f4; padding: 1px 4px; border-radius: 3px; }
  audio { width: 260px; }
  img.psd { width: 100%; max-width: 1060px; display: block; border: 1px solid #eee;
            margin: 0.5em 0 1em; }
  footer { color: #888; font-size: 0.85em; margin-top: 2em; }
"""


def _row(c: ChannelReport, out_dir: str) -> str:
    tr_classes = []
    if c.encryption.encrypted:
        tr_classes.append("enc")
    if not c.decoded_ok:
        tr_classes.append("failed")
    cls = f' class="{" ".join(tr_classes)}"' if tr_classes else ""

    status_badge = (
        '<span class="badge ok">decoded</span>' if c.decoded_ok
        else '<span class="badge fail">no audio</span>')
    enc_badge = (
        f'<span class="badge enc">{html.escape(c.encryption.algorithm or "ENC")}</span>'
        if c.encryption.encrypted else
        '<span class="badge ok">clear</span>')

    wav_cell = ""
    if c.wav_path and c.decoded_ok:
        rel = os.path.relpath(c.wav_path, out_dir).replace(os.sep, "/")
        wav_cell = f'<audio controls preload="none" src="{html.escape(rel)}"></audio>'

    evidence = ""
    if c.encryption.evidence:
        joined = "<br>".join(html.escape(x) for x in c.encryption.evidence[:4])
        evidence = f'<div class="evidence">{joined}</div>'

    keyid = (f"0x{c.encryption.key_id:X}" if c.encryption.key_id is not None
             else "—")
    nac = f"0x{c.nac:X}" if c.nac is not None else "—"
    bw = f"{c.bw_hz/1e3:.1f} kHz"
    duration = f"{c.duration_s:.2f} s"

    return f"""
      <tr{cls}>
        <td><code>{html.escape(c.event_id)}</code></td>
        <td>{c.center_hz/1e6:.4f} MHz</td>
        <td>{c.label or "—"}</td>
        <td>{c.kind}</td>
        <td>{bw}</td>
        <td>{c.snr_db:.1f} dB</td>
        <td>{c.t_start_s:.2f} – {c.t_end_s:.2f} s<br>
            <span class="evidence">{duration}</span></td>
        <td>{c.adapter or "—"}<br>{status_badge}</td>
        <td>{enc_badge}<br>{evidence}</td>
        <td>NAC {nac}<br>
            key {html.escape(keyid)}</td>
        <td>{wav_cell}</td>
      </tr>
    """


def render_html(report: Report) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    psd_rel = "psd.png" if os.path.exists(
        os.path.join(report.out_dir, "psd.png")) else None
    psd_html = (f'<img class="psd" src="{psd_rel}" alt="wideband PSD">'
                if psd_rel else "")

    rows = "\n".join(_row(c, report.out_dir) for c in report.channels)
    stats = f"""
      <div class="stats">
        <div class="stat"><div class="k">Duration</div>
          <div class="v">{report.duration_s:.2f} s</div></div>
        <div class="stat"><div class="k">Channels</div>
          <div class="v">{report.num_channels}</div></div>
        <div class="stat"><div class="k">Decoded</div>
          <div class="v">{report.num_decoded}</div></div>
        <div class="stat"><div class="k">Encrypted</div>
          <div class="v">{report.num_encrypted}</div></div>
        <div class="stat"><div class="k">Center</div>
          <div class="v">{report.center_hz/1e6:.4f} MHz</div></div>
        <div class="stat"><div class="k">Span</div>
          <div class="v">{report.sample_rate_hz/1e6:.2f} MHz</div></div>
      </div>
    """

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>wbdec report</title>
<style>{_CSS}</style>
</head><body>
<h1>wbdec capture report</h1>
<div class="meta">
  Out dir: <code>{html.escape(report.out_dir)}</code><br>
  Generated {generated}
</div>
{stats}
{psd_html}
<table>
  <thead>
    <tr>
      <th>Event</th><th>Frequency</th><th>Protocol</th><th>Kind</th>
      <th>BW</th><th>SNR</th><th>Timing</th><th>Decoder</th>
      <th>Encryption</th><th>IDs</th><th>Play</th>
    </tr>
  </thead>
  <tbody>
{rows}
  </tbody>
</table>
<footer>wbdec · GPL-3.0 · offline wideband digital-voice decoder</footer>
</body></html>
"""
