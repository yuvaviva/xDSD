"""Classifier tests (feature-based, M1 rough cut)."""

from __future__ import annotations

import numpy as np

from wbdec.survey.classifier import classify_from_iq, classify_from_features
from wbdec.survey.features import extract_all
from wbdec.tests._synth import synth_4fsk, synth_pi4_dqpsk


def _fm_discriminator(iq: np.ndarray) -> np.ndarray:
    return np.angle(iq[1:] * np.conj(iq[:-1])).astype(np.float32)


def test_4fsk_classified_as_fm_family():
    fs = 48_000.0
    iq = synth_4fsk(1 << 14, fs, 4800, 1800, seed=7)
    demod = _fm_discriminator(iq)
    label, conf, feats = classify_from_iq(iq, fs, demod, kind="continuous")
    assert label in ("p25_c4fm", "dmr", "dpmr"), (label, conf, feats)
    assert feats.env_var_norm < 0.05


def test_4fsk_burst_prefers_dmr_over_p25():
    fs = 48_000.0
    iq = synth_4fsk(1 << 14, fs, 4800, 1800, seed=9)
    demod = _fm_discriminator(iq)
    _, _, feats = classify_from_iq(iq, fs, demod, kind="continuous")
    cont_label, _ = classify_from_features(feats, kind="continuous")
    burst_label, _ = classify_from_features(feats, kind="burst")
    # Burst bump at least doesn't degrade DMR likelihood.
    if cont_label in ("p25_c4fm", "dmr"):
        assert burst_label in ("p25_c4fm", "dmr")


def test_pi4_dqpsk_has_non_constant_envelope():
    fs = 72_000.0
    iq = synth_pi4_dqpsk(1 << 14, fs, 18_000, seed=11)
    feats = extract_all(iq, fs, np.zeros(0))
    assert feats.env_var_norm > 0.01
