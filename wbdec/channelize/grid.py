"""Protocol → channel-extraction target mapping.

Each protocol family has a characteristic channel bandwidth and a decoder-
appropriate output sample rate. The grid tells the extractor how wide to
low-pass, what target rate to decimate to, and whether to apply a root-
raised-cosine matched filter (TETRA only — linear modulation path).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelTarget:
    label: str               # protocol family
    channel_bw_hz: float     # LPF cutoff (one-sided, full bandwidth = 2× this)
    out_rate_hz: float       # target sample rate for downstream decoder
    apply_rrc: bool          # RRC matched filter after LPF (TETRA only)
    rrc_symbol_rate_hz: float = 0.0
    rrc_rolloff: float = 0.35
    demod_hint: str = "fm"   # "fm" or "linear"


# Conservative: leave some margin beyond the nominal channel width so
# adjacent-channel rejection doesn't clip the in-band energy.
TARGETS: dict[str, ChannelTarget] = {
    "p25_c4fm": ChannelTarget("p25_c4fm", 7_500.0,  48_000.0, False,
                              demod_hint="fm"),
    "dmr":      ChannelTarget("dmr",      7_500.0,  48_000.0, False,
                              demod_hint="fm"),
    "dpmr":     ChannelTarget("dpmr",     3_750.0,  48_000.0, False,
                              demod_hint="fm"),
    "tetra":    ChannelTarget("tetra",    15_000.0, 72_000.0, True,
                              rrc_symbol_rate_hz=18_000.0,
                              rrc_rolloff=0.35,
                              demod_hint="linear"),
    "analog_fm": ChannelTarget("analog_fm", 7_500.0, 48_000.0, False,
                               demod_hint="fm"),
    "unknown":  ChannelTarget("unknown",  10_000.0, 48_000.0, False,
                              demod_hint="fm"),
}


def target_for_label(label: str | None) -> ChannelTarget:
    if not label:
        return TARGETS["unknown"]
    return TARGETS.get(label, TARGETS["unknown"])


def choose_decimation(source_rate_hz: float, target_rate_hz: float) -> int:
    """Largest integer decimation that keeps the output rate ≥ target.

    The remainder after integer decimation is left alone — downstream
    decoders (DSD, tetra-rx) cope with ±1% sample-rate deviation. If the
    math works out exactly (e.g. 10 Msps → 48 kHz needs ×1/208.33), we
    take the floor and accept the small rate error; M3 can rational-resample
    if a decoder is stricter.
    """
    if target_rate_hz <= 0:
        return 1
    dec = int(source_rate_hz // target_rate_hz)
    return max(dec, 1)
