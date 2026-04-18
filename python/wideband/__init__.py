"""Wideband_DMR_Decoder — offline wideband SDR processing for digital-voice.

Ingests a folder of auto-split SDR captures covering up to ~10 MHz, detects
every C4FM (P25) / DMR / dPMR / TETRA carrier in the band, extracts each as
narrowband, routes it to the correct decoder, and flags encryption state.

Auto-split files from the SDR capture tool (HackRF int8, rtl_sdr uint8,
GQRX fc32, SigMF, WAV) are stitched by lexicographic ordering with file-size
gap detection.

Pipeline stages: ingest -> detect (Welch PSD + CA-CFAR + temporal hysteresis)
-> classify (bandwidth + symbol-rate + modulation features) -> extract (freq
shift + LPF + decimate + FM demod) -> decode (gr-dsd or DSD+/DSDcc/dsd-fme
via subprocess; osmocom-tetra tetra-rx for TETRA) -> encryption probe
(P25 algid, DMR PI header, TETRA MAC-ENCR) -> report (per-channel WAV +
JSON metadata).

Public entry point: `dsd.wideband.run_job(config)` /
`python -m dsd.wideband run <config.json>`.
"""

from .config import WidebandConfig, load_config
from .orchestrate.pipeline import run_job

__version__ = "0.1.0"
__project_name__ = "Wideband_DMR_Decoder"

__all__ = ["WidebandConfig", "load_config", "run_job", "__version__",
           "__project_name__"]

