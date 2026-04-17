"""Crypto detection + attack module unit tests."""

from __future__ import annotations

import numpy as np

from dsd.wideband.crypto import probe_p25_encryption, probe_dmr_pi_header
from dsd.wideband.crypto.attacks import available_attacks
from dsd.wideband.crypto.attacks.iv_reuse import detect_iv_reuse
from dsd.wideband.crypto.attacks.p25_adp import attack_p25_adp, _rc4_keystream, _derive_adp_key


def test_p25_clear_detection():
    state = probe_p25_encryption(0x80, 0)
    assert not state.encrypted
    assert state.algorithm is None


def test_p25_aes_detection():
    state = probe_p25_encryption(0x84, 0x1234)
    assert state.encrypted
    assert state.algorithm == "AES-256"
    assert state.recoverable is False


def test_dmr_pi_basic_privacy():
    hdr = bytes([0x21, 0x03, 0, 0, 0, 0])
    state = probe_dmr_pi_header(hdr)
    assert state.encrypted
    assert state.recoverable is True
    assert state.algorithm == "BASIC-PRIVACY"


def test_iv_reuse_flags_duplicates():
    res = detect_iv_reuse([1, 2, 1, 3, 2])
    assert res.succeeded
    assert "2 MI value" in res.notes or "2 MI value(s)" in res.notes


def test_p25_adp_finds_planted_key():
    key = bytes.fromhex("0102030405060708090a")
    mi = 0x11223344
    pt = b"CRIB TEXT HELLO" + b"\x00" * 100
    ks = _rc4_keystream(_derive_adp_key(key, mi), len(pt))
    ct = bytes(p ^ k for p, k in zip(pt, ks))
    wordlist = [bytes.fromhex("00" * 10), key, bytes.fromhex("ff" * 10)]
    res = attack_p25_adp(ct, mi, crib=b"CRIB", wordlist=wordlist,
                        max_cpu_seconds=5.0, algid=0x85)
    assert res.succeeded
    assert res.key_hex == key.hex()


def test_available_attacks_registry():
    reg = available_attacks()
    assert {"iv_reuse", "p25_adp", "p25_des_known_key", "dmr_bp",
            "tetra_tea1"} <= set(reg.keys())
