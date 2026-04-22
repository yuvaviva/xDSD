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

## Status: M1 shipped

- **Capture** — mmap-backed readers for HackRF int8 / rtl_sdr uint8 /
  GQRX fc32 / SigMF / WAV, contiguous stitching of split files with gap
  detection, virtual SigMF view (`capture.sigmf-meta`) over the stitched stream.
- **Survey** — streaming Welch PSD + CA-CFAR peak detection + TDMA-aware
  burst tracker + continuous tracker + feature-based classifier.
  Outputs `survey.json` + `psd.png`.
- **CLI** — `wbdec ingest` and `wbdec survey` implemented.

Milestones M2 (channelize), M3 (decode), M4 (analyze/report), M5
(trunking + end-to-end run) to follow.

## Install

```bash
pip install -e ".[all]"
```

Windows + radioconda works out of the box (radioconda already provides
numpy/scipy/matplotlib).

## Run

```bash
# 1. Probe a folder:
wbdec ingest /path/to/captures --sample-rate 10e6 --center-hz 450e6 \
    --format hackrf_int8 --out wbdec_out

# 2. Detect every signal in the band:
wbdec survey /path/to/captures --sample-rate 10e6 --center-hz 450e6 \
    --format hackrf_int8 --out wbdec_out
```

Output in `wbdec_out/`:

- `capture.sigmf-meta` — virtual SigMF descriptor of the stitched stream
- `ingest_manifest.json` — file list + duration estimate
- `survey.json` — every detected signal (freq, time, bandwidth, SNR, kind,
  rough classification)
- `psd.png` — wideband averaged spectrum

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## License

GPL-3.0-or-later.
