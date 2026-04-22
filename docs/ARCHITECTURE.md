# wbdec architecture

Five stages, one artifact per stage, all on disk.

```
folder of split IQ (minutes of 10 Msps)
      │
      ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 1. CAPTURE       split_files → SigMF virtual view                   │
│                  mmap, no full buffer; produces capture.sigmf-meta  │
└─────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. SURVEY        streaming Welch + CA-CFAR                          │
│                  two trackers:                                      │
│                    • continuous  (P25 conv., dPMR, analog FM)       │
│                    • burst       (DMR slots, TETRA frames)          │
│                  feature-based classifier → label + confidence      │
│                  output: survey.json  (freq, time, label, snr, kind)│
└─────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. CHANNELIZE    one polyphase filter bank pass over the capture    │
│                  snaps detected channels onto protocol-appropriate  │
│                  grids (12.5 / 6.25 / 25 kHz)                       │
│                  output: channels/ch_<id>.sigmf-{meta,data}         │
│                  - FM-family  → 48 kHz cf32                         │
│                  - TETRA      → 72 kHz cf32 (linear; RRC applied)   │
└─────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. DECODE        pluggable ProtocolAdapter registry                 │
│                    - dsd_fme     (subprocess, Windows default)      │
│                    - gr_dsd      (in-process, optional)             │
│                    - tetra_rx    (subprocess, optional)             │
│                    - tetra_native(in-tree π/4-DQPSK → sym stream)   │
│                  ProcessPoolExecutor + backpressure                 │
│                  output: calls/<ts>_<proto>_<freq>_<tgid>.wav       │
│                          channels/ch_<id>.frames.jsonl              │
└─────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 5. ANALYZE       pure metadata pass over frames.jsonl               │
│                  encryption parsers  (P25 algid, DMR PI, TETRA ENCR)│
│                  trunking follower   (P25 LCCH, DMR CSBK)           │
│                  output: report.json  +  report.html                │
│                          calls/index.m3u  (playlist)                │
└─────────────────────────────────────────────────────────────────────┘
```

## Design principles

1. **SigMF is the lingua franca between stages.** Every intermediate is a
   SigMF pair on disk. This lets you re-run any stage independently, swap a
   decoder, debug with external tools (inspectrum, gqrx), and parallelise
   trivially.

2. **Memory-mapped I/O end-to-end** (`numpy.memmap` in
   `wbdec.capture.readers`). A 10-minute 10 Msps HackRF dump (~75 GB) costs
   you the currently-touched chunk, not the whole file.

3. **One unified polyphase channel bank** in stage 3, not per-event
   xlate+decimate. Detected channels snap onto a uniform 12.5 kHz grid
   (6.25 for dPMR, 25 for TETRA) and a single PFB extracts them all.

4. **Protocol adapters are plugins.** Adding a new decoder means one
   module in `wbdec/decode/` implementing the `ProtocolAdapter` interface —
   no pipeline surgery. Built-ins: gr-dsd, dsd-fme, tetra-rx, tetra-native.

5. **TETRA has its own demod path.** Root-raised-cosine matched filter
   into coherent π/4-DQPSK detection, bypassing the FM discriminator that
   works for P25/DMR/dPMR.

6. **TDMA-aware tracker** (`tracker_burst.py`) keeps a track alive across
   silent slots by sliding-window duty cycle, not absence counting.

7. **Encryption detection is a pure read pass** (stage 5) over the
   JSONL frame streams produced by decoders. No cryptanalysis.

## Repository layout

```
wbdec/
  capture/       # stage 1 — mmap readers + split stitching + SigMF view
  survey/        # stage 2 — PSD + CFAR + trackers + classifier
  channelize/    # stage 3 (M2)
  demod/         # stage 3/4 support — FM discriminator, RRC, π/4-DQPSK
  decode/        # stage 4 (M3) — adapter registry
  encryption/    # stage 5 (M4)
  trunking/      # stage 5 (M5)
  orchestrate/   # pool + pipeline
  io/            # parquet, sigmf, html report
  tests/
```
