"""Classification unit tests using synthesised baseband signals."""

from __future__ import annotations

import numpy as np

from dsd.wideband.classify import classify_event
from dsd.wideband.extract import fm_discriminator
from dsd.wideband.tests._synth import synth_4fsk, synth_pi4_dqpsk


def test_classify_4fsk_is_not_tetra():
    # Unshaped 4FSK at 4800 sym/s lands somewhere in the FM-4FSK family
    # (p25/dmr/dpmr). What matters is it does NOT classify as tetra.
    fs = 48_000.0
    bb = synth_4fsk(1 << 14, fs, 4800, 1800, seed=7)
    demod = fm_discriminator(bb, gain=1.0)
    label, conf, feats = classify_event(bb, fs, demod)
    assert label in ("p25_c4fm", "dmr", "dpmr", "unknown"), (label, conf, feats)
    assert feats.envelope_variance < 0.05  # constant-envelope FM


def test_classify_tetra_like():
    fs = 72_000.0
    bb = synth_pi4_dqpsk(1 << 14, fs, 18_000, seed=11)
    demod = fm_discriminator(bb, gain=1.0)
    label, conf, feats = classify_event(bb, fs, demod)
    assert label in ("tetra", "p25_c4fm", "dmr", "unknown"), label
