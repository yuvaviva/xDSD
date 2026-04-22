# wbdec — Wideband Digital-Voice Decoder

Offline pipeline for reading **auto-split SDR recordings** (HackRF, rtl_sdr,
GQRX, SigMF, WAV) covering up to **~10 MHz** of spectrum, detecting every
**C4FM (P25) / DMR / dPMR / TETRA** carrier in the band, extracting each as
narrowband, routing it to the correct decoder, and **flagging encryption**.

Five stages, each runnable and rerunnable independently:

```
capture → survey → channelize → decode → analyze
```

Each stage takes files on disk and produces files on disk — swap a decoder,
retune detection thresholds, regenerate a report, all without re-running
earlier stages.

## Status: all five milestones shipped

- **M1 Capture + Survey** — mmap readers (HackRF int8 / rtl_sdr uint8 /
  GQRX fc32 / SigMF / WAV), split stitching with gap detection, streaming
  Welch + CA-CFAR + continuous & TDMA-burst trackers + feature-based
  classifier. Outputs `survey.json` + `psd.png`.
- **M2 Channelize** — one streaming source pass extracts every detected
  event into its own SigMF cf32 file. Per-protocol target rates (48 kHz
  for FM-family, 72 kHz for TETRA with RRC matched filter applied).
- **M3 Decode** — pluggable `ProtocolAdapter` registry. Built-ins:
  `dsd_fme`, `gr_dsd`, `tetra_rx`, `tetra_native`. ProcessPoolExecutor
  with bounded backpressure.
- **M4 Analyze** — pure metadata pass over `frames/*.jsonl` →
  encryption findings (P25 algid, DMR PI, TETRA MAC-ENCR), single-file
  HTML report, M3U playlist of decoded calls.
- **M5 Trunking + `wbdec run`** — log-driven control-channel event
  extraction (P25 LCCH / DMR CSBK), per-channel talkgroup/source
  annotation with predictive grant matching, single-command end-to-end
  pipeline runner.

## Install

```bash
pip install -e ".[all]"
```

Windows + radioconda works out of the box (radioconda already provides
numpy/scipy/matplotlib).

## Run

One command runs every stage end-to-end:

```bash
wbdec run config.json
```

Or each stage independently (each rerunnable, each writes to disk):

```bash
wbdec ingest     /path/to/captures --sample-rate 10e6 --center-hz 450e6 \
                 --format hackrf_int8
wbdec survey     /path/to/captures --sample-rate 10e6 --center-hz 450e6 \
                 --format hackrf_int8
wbdec channelize --config config.json
wbdec decode     --config config.json
wbdec analyze    --config config.json
```

Output in `wbdec_out/`:

- `capture.sigmf-meta` — virtual SigMF descriptor of the stitched stream
- `ingest_manifest.json` — file list + duration estimate
- `survey.json` — every detected signal (freq, time, bandwidth, SNR, kind,
  classification + confidence)
- `psd.png` — wideband averaged spectrum
- `channels/ch_*.sigmf-{meta,data}` — per-event narrowband baseband
- `calls/<event_id>.wav` — decoded audio per channel
- `frames/<event_id>.jsonl` — decoder frame stream
- `decode.json` — aggregate decode summary
- `report.json` — per-channel encryption + trunking findings
- `report.html` — single-file browser report (audio playback + PSD)
- `calls/index.m3u` — playlist of decoded calls

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## License

GPL-3.0-or-later.
