"""wbdec — Wideband Digital-Voice Decoder.

Offline pipeline for reading auto-split wideband SDR recordings (HackRF,
rtl_sdr, GQRX, SigMF, WAV) covering up to ~10 MHz, detecting every
C4FM / DMR / dPMR / TETRA carrier in the band, extracting each as narrowband,
routing it to the correct decoder, and flagging encryption.

Architecture (five stages, each runnable and rerunnable independently):

    capture → survey → channelize → decode → analyze

Public entry points: ``wbdec`` CLI (``wbdec survey|channelize|decode|analyze|run``)
and ``wbdec.run_pipeline(config)``.
"""

__version__ = "0.1.0"
__project_name__ = "wbdec"

from .config import Config, load_config  # noqa: E402

__all__ = ["Config", "load_config", "__version__", "__project_name__"]
