"""Detection layer: averaged PSD + CFAR peak picker + temporal hysteresis."""

from .events import SignalEvent
from .psd import averaged_psd, stream_frames
from .cfar import ca_cfar, group_peaks
from .tracker import EventTracker

__all__ = ["SignalEvent", "averaged_psd", "stream_frames",
           "ca_cfar", "group_peaks", "EventTracker"]
