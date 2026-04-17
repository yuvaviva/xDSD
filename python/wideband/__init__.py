"""dsd.wideband — offline wideband SDR processing for digital-voice protocols.

Ingests a folder of auto-split SDR captures covering up to ~10 MHz, detects
C4FM / DMR / dPMR / TETRA carriers, extracts each as narrowband, routes them
to the appropriate decoder, and flags encryption state.

Public entry point: `dsd.wideband.run_job(config)`.
"""

from .config import WidebandConfig, load_config
from .orchestrate.pipeline import run_job

__all__ = ["WidebandConfig", "load_config", "run_job"]
