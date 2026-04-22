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
# placeholders for M2+
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

    # M2+
    for stage in ("channelize", "decode", "analyze", "run"):
        sp = sub.add_parser(stage, help=f"{stage} — not implemented yet")
        sp.set_defaults(func=_cmd_not_implemented(stage))

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
