# Wideband_DMR_Decoder

Offline wideband SDR pipeline that **reads auto-split recordings from a folder
covering up to ~10 MHz**, detects every **C4FM (P25) / DMR / dPMR / TETRA**
carrier in the band, extracts each as a narrowband channel, routes it to the
correct decoder, and **flags encryption state** per channel. Optional passive
key-recovery attack modules are included for weak algorithms (P25 ADP/DES,
DMR Basic Privacy, TETRA TEA1).

Forked from [gr-dsd](https://github.com/argilo/gr-dsd) — the Python
sub-package `dsd.wideband` is the new work; the gr-dsd C++ block is reused
as one of the two decoder backends.

---

## What it does

```
folder of split IQ files (10 MHz wide)
      │
      ▼
Ingest        HackRF int8 / rtl_sdr uint8 / GQRX fc32 / SigMF / WAV
              + ContiguousStream: sort by filename, stitch splits,
                detect gaps from file-size vs sample-rate
      │
      ▼
Detect        Welch-averaged PSD over the full 10 MHz span
              CA-CFAR peak picker per frame
              Temporal hysteresis tracker → SignalEvent list
      │
      ▼
Classify      Occupied bandwidth + cyclostationary symbol-rate
              Level histogram (2FSK vs 4FSK)
              Fourth-power phase variance (FM vs π/4-DQPSK)
              Rule tree → {p25_c4fm, dmr, dpmr, tetra, unknown}
      │
      ▼
Extract       Freq shift → FIR LPF → integer decimate → resample to 48 kHz
              FM discriminator (np.angle(conj(x[:-1]) * x[1:]))
      │
      ▼
Decode        P25/DMR: gr-dsd block, OR DSD+/DSDcc/dsd-fme via subprocess
              TETRA:   osmocom-tetra tetra-rx subprocess
              dPMR:    dsd-fme subprocess (-fm) OR detect-only stub
      │
      ▼
Encryption    P25 algid/keyid from dsd_state
              DMR PI header parse (new; not in upstream dsd)
              TETRA MAC-ENCR from tetra-rx log
              Optional M6b passive attacks: IV reuse, P25 ADP dict,
              DMR Basic Privacy dict, DES known-key, TETRA TEA1 distinguisher
      │
      ▼
Report        per-channel WAV (8 kHz int16), JSON metadata, PSD PNG,
              run-level report.json
```

---

## Install

### Standalone (Windows + radioconda, or any Python 3.8+ env)

```bash
git clone https://github.com/<your-fork>/Wideband_DMR_Decoder.git
cd Wideband_DMR_Decoder
pip install -e ".[all]"
```

That installs the package and pulls `numpy`, `scipy`, `pyyaml`, `matplotlib`,
`sigmf`, `cryptography`, and `pytest`.

For **voice decoding on Windows** you do **not** need to build gr-dsd — just
grab a `dsd-fme` Windows portable build from
[lwvmobile/dsd-fme releases](https://github.com/lwvmobile/dsd-fme/releases)
and point the config at `dsd-fme.exe`.

For **voice decoding on Linux/BSD with gr-dsd**: build the C++ side of this
repo the usual way (`cmake . && make && sudo make install && sudo ldconfig`)
and keep `decode.dsd_backend = "gr"` in the config.

---

## Quick start

```bash
# Probe a folder (dumps manifest.json with file list + duration estimate):
python -m dsd.wideband ingest /path/to/captures --format hackrf_int8 \
    --sample-rate 10e6 --out manifest.json

# Detect signals only (no decode, for survey):
python -m dsd.wideband detect /path/to/captures \
    --sample-rate 10e6 --format hackrf_int8

# Full pipeline — copy the example config, edit ingest.folder/sample_rate/
# center_hz and decode.dsd_binary, then:
cp python/wideband/example_config.json my_config.json
# ... edit my_config.json ...
python -m dsd.wideband run my_config.json
```

Output folder layout:

```
wideband_out/
  report.json           # run-level + per-event summary
  psd.png               # wideband averaged PSD plot
  ch_450123456/
    voice_8k.wav        # decoded audio (one per detected channel)
    dsd.log             # raw decoder log (subprocess backend)
```

---

## Configuration cheat sheet

`python/wideband/example_config.json` is the template. Key fields:

```json
{
  "ingest": {
    "folder":       "/path/to/captures",
    "sample_rate":  10000000.0,
    "center_hz":    450000000.0,
    "format":       "hackrf_int8"
  },
  "detect":   { "nperseg": 8192, "nav": 32, "cfar_pfa": 0.0001,
                "min_persist_frames": 2 },
  "decode":   {
    "dsd_backend":  "subprocess",
    "dsd_binary":   "C:\\Tools\\dsd-fme\\dsd-fme.exe",
    "dsd_flavor":   "dsd_fme",
    "dsd_extra_args": [],
    "enable_tetra": false,
    "enable_dpmr":  true
  },
  "crypto":   {
    "detect":              true,
    "enable_key_recovery": false
  },
  "output":   { "out_dir": "wideband_out", "write_wav": true,
                "write_spectrogram_png": true }
}
```

Supported `dsd_backend` values: `"gr"` (in-process gr-dsd block) or
`"subprocess"` (external CLI).
Supported `dsd_flavor` values (for subprocess): `dsd_fme`, `dsd`, `dsdcc`, `dsdplus`.

---

## Supported protocols

| Protocol     | Detect | Classify | Decode (gr) | Decode (subprocess) | Encryption detect |
|--------------|:------:|:--------:|:-----------:|:-------------------:|:-----------------:|
| P25 C4FM     |   ✓    |    ✓     |      ✓      |         ✓           |        ✓          |
| DMR          |   ✓    |    ✓     |      ✓      |         ✓           |  PI header (new)  |
| dPMR         |   ✓    |    ✓     |      –      |   ✓ (dsd-fme -fm)   |      deferred     |
| TETRA        |   ✓    |    ✓     |      –      |   ✓ (tetra-rx)      |  MAC-ENCR log     |
| NXDN48/96    |   ✓    |    –     |      ✓      |         ✓           |        –          |
| D-STAR       |   ✓    |    –     |      ✓      |         ✓           |        –          |
| ProVoice     |   –    |    –     |      ✓      |         ✓           |        –          |

---

## Passive key-recovery (optional — M6b)

Gated behind `crypto.enable_key_recovery` and per-module toggles. **Passive
only** — no transmission, no active probing.

| Module                    | Algorithm             | What it does                                           |
|---------------------------|-----------------------|--------------------------------------------------------|
| `iv_reuse`                | any stream cipher     | Flags repeated MI/IV across frames                     |
| `p25_adp`                 | P25 ADP (RC4)         | Bounded dictionary attack against a crib              |
| `p25_des_known_key`       | P25 DES-OFB           | Decrypt with a user-supplied key (no bruteforce)      |
| `dmr_bp`                  | DMR Basic Privacy     | 40-bit scrambler dictionary attack                    |
| `tetra_tea1`              | TETRA TEA1            | Ciphertext distinguisher only (no key recovery)       |

Strong algorithms (AES, 3DES, TEA2-4) always report `recoverable=false`
with ciphertext statistics only — no attack is attempted.

---

## Tests

15 unit tests + 1 end-to-end synthesis test (1s wideband IQ with two 4FSK
carriers) + 3 subprocess-runner tests. Runs without GNU Radio installed:

```bash
pip install -e ".[test]"
python -m pytest python/wideband/tests/ -q
# 19 passed
```

---

## Roadmap

Implemented in this fork:

- **M1** Ingest — HackRF/RTL/fc32/SigMF/WAV + split stitching + gap detection
- **M2** Detect — Welch PSD + CA-CFAR + temporal hysteresis
- **M3** Classify + Extract + Decode (P25/DMR/dPMR via dsd-fme; also gr-dsd)
- **M4** TETRA via osmocom-tetra subprocess
- **M5** dPMR via dsd-fme `-fm` (previously stub)
- **M6a** Encryption detection (P25/DMR/TETRA)
- **M6b** Passive key-recovery modules (opt-in)
- **M7** CLI + config + JSON/PNG reporting

Known limits / future work:

- Serial pipeline — multiprocessing worker pool is scaffolded but not wired
- DMR PI header bits not surfaced by upstream dsd yet — parser exists but
  needs a bridge through the subprocess log or a dsd patch
- Real-time / streaming operation is out of scope
- Frequency-hopping trunked systems (P25p2, EDACS EA) need a follow-up
  control-channel tracker

---

## License

GPL-3.0-or-later (inherits from gr-dsd / DSD / mbelib).

---

## Credits

- gr-dsd — Clayton Smith
- DSD — szechyjs
- dsd-fme — lwvmobile
- mbelib
- osmocom-tetra
- Wideband_DMR_Decoder sub-package — new work in this fork
