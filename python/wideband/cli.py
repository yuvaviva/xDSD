"""`python -m dsd.wideband` command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
import sys

from .config import load_config, WidebandConfig, IngestConfig
from .orchestrate.pipeline import run_job


def _cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    report = run_job(cfg)
    print(f"Wrote {report['num_events']} events to {cfg.output.out_dir}")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    from .ingest import ContiguousStream
    stream = ContiguousStream(
        folder=args.folder,
        sample_rate=args.sample_rate,
        center_hz=args.center_hz,
        format_hint=args.format,
    )
    total = stream.total_samples_estimate()
    manifest = {
        "folder": args.folder,
        "files": stream.files,
        "sample_rate_hz": stream.sample_rate,
        "center_hz": stream.center_hz,
        "estimated_samples": total,
        "estimated_duration_s": total / stream.sample_rate if stream.sample_rate else 0,
    }
    out = args.out or "ingest_manifest.json"
    with open(out, "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"Wrote manifest to {out}: {len(stream.files)} files, "
          f"~{manifest['estimated_duration_s']:.1f} s")
    return 0


def _cmd_detect(args: argparse.Namespace) -> int:
    cfg = load_config(args.config) if args.config else WidebandConfig(
        ingest=IngestConfig(folder=args.folder,
                            sample_rate=args.sample_rate or 10_000_000.0,
                            center_hz=args.center_hz or 0.0,
                            format=args.format),
    )
    report = run_job(cfg)
    print(f"{report['num_events']} event(s) detected")
    for ev in report["events"]:
        e = ev["event"]
        print(f"  {e['center_hz']/1e6:8.4f} MHz  BW {e['bw_hz']/1e3:6.2f} kHz  "
              f"SNR {e['snr_db']:5.1f} dB  label={e.get('label')}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser("dsd.wideband")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run the full pipeline from a config file.")
    p_run.add_argument("config")
    p_run.set_defaults(func=_cmd_run)

    p_ing = sub.add_parser("ingest", help="Probe a folder and emit a manifest.")
    p_ing.add_argument("folder")
    p_ing.add_argument("--sample-rate", type=float, default=10_000_000.0)
    p_ing.add_argument("--center-hz", type=float, default=0.0)
    p_ing.add_argument("--format", default=None)
    p_ing.add_argument("--out", default=None)
    p_ing.set_defaults(func=_cmd_ingest)

    p_det = sub.add_parser("detect", help="Detect signals in a folder (no decode).")
    p_det.add_argument("folder", nargs="?")
    p_det.add_argument("--config", default=None)
    p_det.add_argument("--sample-rate", type=float, default=None)
    p_det.add_argument("--center-hz", type=float, default=None)
    p_det.add_argument("--format", default=None)
    p_det.set_defaults(func=_cmd_detect)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
