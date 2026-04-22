"""`wbdec` command-line entry point.

Subcommands (M1 ships `survey` + `ingest`; rest come online in M2+):

    wbdec ingest <folder> [--format ...] [--out manifest.json]
    wbdec survey <folder> [--config cfg.json] [--sample-rate] [--center-hz]
                          [--format] [--out out_dir]
    wbdec channelize <folder>     # M2
    wbdec decode <channels>       # M3
    wbdec analyze <channels>      # M4
    wbdec run <config.yaml>       # M5

Each subcommand is runnable independently; nothing hidden.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from .config import CaptureConfig, Config, SurveyConfig, load_config


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------

def _cmd_ingest(args: argparse.Namespace) -> int:
    from .capture.splits import SplitSet
    from .capture.sigmf_view import VirtualSigMF, write_view_meta
    ss = SplitSet.discover(
        folder=args.folder,
        sample_rate_hz=args.sample_rate or 10_000_000.0,
        center_hz=args.center_hz or 0.0,
        fmt=args.format,
    )
    view = VirtualSigMF.from_split_set(ss)
    out_dir = args.out or "wbdec_out"
    meta_path = write_view_meta(view, out_dir)
    manifest = {
        "folder": args.folder,
        "format": ss.fmt,
        "files": ss.files,
        "sample_rate_hz": ss.sample_rate_hz,
        "center_hz": ss.center_hz,
        "total_samples": ss.total_samples,
        "duration_s": ss.duration_s,
        "sigmf_meta": meta_path,
    }
    with open(os.path.join(out_dir, "ingest_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"{len(ss.files)} file(s), {ss.total_samples:,} samples, "
          f"{ss.duration_s:.3f} s at {ss.sample_rate_hz/1e6:.3f} Msps")
    print(f"manifest: {os.path.join(out_dir, 'ingest_manifest.json')}")
    print(f"sigmf meta: {meta_path}")
    return 0


# ---------------------------------------------------------------------------
# survey
# ---------------------------------------------------------------------------

def _config_from_args(args: argparse.Namespace) -> Config:
    if args.config:
        return load_config(args.config)
    if not args.folder:
        raise SystemExit("either --config or a folder must be given")
    return Config(capture=CaptureConfig(
        folder=args.folder,
        sample_rate_hz=args.sample_rate or 10_000_000.0,
        center_hz=args.center_hz or 0.0,
        format=args.format,
    ))


def _cmd_survey(args: argparse.Namespace) -> int:
    from .survey.run import run_survey
    cfg = _config_from_args(args)
    if args.out:
        cfg.out_dir = args.out
    result = run_survey(cfg)
    print(f"{result.num_frames} frames, {len(result.events)} events, "
          f"{result.duration_s:.2f} s of capture")
    for ev in result.events[:20]:
        print(f"  {ev.kind:<10} {ev.center_hz/1e6:10.4f} MHz  "
              f"BW {ev.bw_hz/1e3:6.2f} kHz  "
              f"SNR {ev.snr_db:5.1f} dB  "
              f"hits {ev.hits:4d}  duty {ev.duty_cycle:.2f}")
    if len(result.events) > 20:
        print(f"  ... {len(result.events) - 20} more events in survey.json")
    print(f"wrote {os.path.join(cfg.out_dir, 'survey.json')}")
    return 0


# ---------------------------------------------------------------------------
# channelize (M2)
# ---------------------------------------------------------------------------

def _cmd_channelize(args: argparse.Namespace) -> int:
    from .channelize.run import run_channelize
    cfg = _config_from_args(args)
    if args.out:
        cfg.out_dir = args.out
    metas = run_channelize(cfg, survey_path=args.survey)
    print(f"channelized {len(metas)} event(s) into "
          f"{os.path.join(cfg.out_dir, cfg.channelize.out_dir)}/")
    for eid, meta in list(metas.items())[:20]:
        g = meta["global"]
        print(f"  {eid}  {g.get('wbdec:label') or '?':<10} "
              f"{g['core:sample_rate']/1e3:7.2f} ksps  "
              f"{g['wbdec:samples']:>8,} samples  "
              f"rrc={g['wbdec:rrc_applied']}")
    if len(metas) > 20:
        print(f"  ... {len(metas) - 20} more channels")
    return 0


# ---------------------------------------------------------------------------
# decode (M3)
# ---------------------------------------------------------------------------

def _cmd_decode(args: argparse.Namespace) -> int:
    from .decode.run import run_decode
    cfg = _config_from_args(args)
    if args.out:
        cfg.out_dir = args.out
    summary = run_decode(cfg, channels_dir=args.channels_dir,
                         workers=args.workers)
    print(f"channels: {summary['num_channels']}   "
          f"decoded ok: {summary['num_decoded']}   "
          f"skipped: {summary['num_skipped']}")
    shown = 0
    for eid, r in summary["results"].items():
        if shown >= 20:
            break
        shown += 1
        line = (f"  {eid}  {r['protocol']:<10} via {r['adapter']:<12} "
                f"ok={r['ok']!s:<5} frames={r['n_frames']}")
        if r.get("nac") is not None:
            line += f"  nac=0x{r['nac']:X}"
        if r.get("algid") is not None:
            line += f"  algid=0x{r['algid']:02X}"
        if r.get("error"):
            line += f"  err={r['error']}"
        print(line)
    if summary["num_channels"] > shown:
        print(f"  ... {summary['num_channels'] - shown} more channels in decode.json")
    return 0


# ---------------------------------------------------------------------------
# analyze (M4)
# ---------------------------------------------------------------------------

def _cmd_analyze(args: argparse.Namespace) -> int:
    from .analyze.run import run_analyze
    cfg = _config_from_args(args)
    if args.out:
        cfg.out_dir = args.out
    report = run_analyze(cfg)
    print(f"channels: {report.num_channels}   decoded: {report.num_decoded}   "
          f"encrypted: {report.num_encrypted}")
    print(f"report.json: {os.path.join(cfg.out_dir, 'report.json')}")
    if cfg.analyze.write_html:
        print(f"report.html: {os.path.join(cfg.out_dir, 'report.html')}")
    print(f"playlist:    {os.path.join(cfg.out_dir, cfg.decode.out_dir, 'index.m3u')}")
    return 0


# ---------------------------------------------------------------------------
# run (M5) — full end-to-end pipeline
# ---------------------------------------------------------------------------

def _cmd_run(args: argparse.Namespace) -> int:
    from .orchestrate.pipeline import run_pipeline
    cfg = load_config(args.config)
    if args.out:
        cfg.out_dir = args.out
    result = run_pipeline(cfg)
    print(f"survey events:     {result.survey_events}")
    print(f"channels:          {result.channels}")
    print(f"decoded ok:        {result.decoded_ok}")
    print(f"encrypted:         {result.encrypted}")
    print(f"trunking events:   {result.trunking_events}")
    print(f"out_dir:           {result.out_dir}")
    print(f"  report.json:     {os.path.join(result.out_dir, 'report.json')}")
    print(f"  report.html:     {os.path.join(result.out_dir, 'report.html')}")
    print(f"  playlist:        {os.path.join(result.out_dir, cfg.decode.out_dir, 'index.m3u')}")
    return 0


# ---------------------------------------------------------------------------
# placeholders (none left)
# ---------------------------------------------------------------------------

def _cmd_not_implemented(stage: str):
    def _run(args: argparse.Namespace) -> int:
        print(f"{stage}: not implemented yet (lives in later milestone)",
              file=sys.stderr)
        return 2
    return _run


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser("wbdec", description="Wideband digital-voice decoder.")
    sub = p.add_subparsers(dest="cmd", required=True)

    # ingest
    p_ing = sub.add_parser("ingest", help="discover splits and write a SigMF view")
    p_ing.add_argument("folder")
    p_ing.add_argument("--sample-rate", type=float, default=None)
    p_ing.add_argument("--center-hz", type=float, default=None)
    p_ing.add_argument("--format", default=None)
    p_ing.add_argument("--out", default=None)
    p_ing.set_defaults(func=_cmd_ingest)

    # survey
    p_sv = sub.add_parser("survey", help="detect signals across the band")
    p_sv.add_argument("folder", nargs="?")
    p_sv.add_argument("--config", default=None)
    p_sv.add_argument("--sample-rate", type=float, default=None)
    p_sv.add_argument("--center-hz", type=float, default=None)
    p_sv.add_argument("--format", default=None)
    p_sv.add_argument("--out", default=None)
    p_sv.set_defaults(func=_cmd_survey)

    # channelize (M2)
    p_ch = sub.add_parser("channelize",
                          help="extract each surveyed event as a SigMF channel file")
    p_ch.add_argument("folder", nargs="?")
    p_ch.add_argument("--config", default=None)
    p_ch.add_argument("--sample-rate", type=float, default=None)
    p_ch.add_argument("--center-hz", type=float, default=None)
    p_ch.add_argument("--format", default=None)
    p_ch.add_argument("--survey", default=None,
                      help="path to survey.json (default: <out>/survey.json)")
    p_ch.add_argument("--out", default=None)
    p_ch.set_defaults(func=_cmd_channelize)

    # decode (M3)
    p_dec = sub.add_parser("decode", help="run the right decoder on each channel")
    p_dec.add_argument("folder", nargs="?")
    p_dec.add_argument("--config", default=None)
    p_dec.add_argument("--sample-rate", type=float, default=None)
    p_dec.add_argument("--center-hz", type=float, default=None)
    p_dec.add_argument("--format", default=None)
    p_dec.add_argument("--channels-dir", default=None)
    p_dec.add_argument("--out", default=None)
    p_dec.add_argument("--workers", type=int, default=None)
    p_dec.set_defaults(func=_cmd_decode)

    # analyze (M4)
    p_an = sub.add_parser("analyze", help="aggregate stages 1–4 → report.html / report.json")
    p_an.add_argument("folder", nargs="?")
    p_an.add_argument("--config", default=None)
    p_an.add_argument("--sample-rate", type=float, default=None)
    p_an.add_argument("--center-hz", type=float, default=None)
    p_an.add_argument("--format", default=None)
    p_an.add_argument("--out", default=None)
    p_an.set_defaults(func=_cmd_analyze)

    # run (M5) — full end-to-end
    p_run = sub.add_parser("run",
                           help="run all five stages back-to-back from a config")
    p_run.add_argument("config")
    p_run.add_argument("--out", default=None)
    p_run.set_defaults(func=_cmd_run)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
