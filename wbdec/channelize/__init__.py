"""Channelize stage: extract each surveyed event as its own SigMF channel.

One pass over the source capture; per-event state machines shift + LPF +
decimate in a streaming, memory-bounded fashion. Optional RRC matched
filter is applied for TETRA (linear modulation) so stage-4 decoders see
pulse-shaped baseband at the right rate.
"""

from .grid import (
    ChannelTarget,
    TARGETS,
    target_for_label,
    choose_decimation,
)
from .rrc import rrc_taps
from .extractor import ChannelExtractor
from .writer import SigMFChannelWriter
from .run import run_channelize

__all__ = [
    "ChannelTarget",
    "TARGETS",
    "target_for_label",
    "choose_decimation",
    "rrc_taps",
    "ChannelExtractor",
    "SigMFChannelWriter",
    "run_channelize",
]
