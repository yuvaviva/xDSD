"""Encryption-parser unit tests."""

from __future__ import annotations

from wbdec.encryption import (
    EncryptionFinding, probe_dmr_frames, probe_frames, probe_p25_frames,
    probe_tetra_frames,
)


# ---------------------------------------------------------------------------
# P25
# ---------------------------------------------------------------------------

def test_p25_clear():
    f = probe_p25_frames([
        {"type": "P25_HDU", "algid": 0x80, "keyid": 0},
        {"type": "P25_LDU1"},
    ])
    assert f.encrypted is False
    assert f.algorithm is None
    assert f.algorithm_id == 0x80


def test_p25_aes():
    f = probe_p25_frames([
        {"type": "P25_HDU", "algid": 0x84, "keyid": 0x1234},
    ])
    assert f.encrypted is True
    assert f.algorithm == "AES-256"
    assert f.key_id == 0x1234


def test_p25_adp_via_evidence_line():
    f = probe_p25_frames([
        {"type": "ENCRYPTION_EVIDENCE",
         "log_line": "HDU algid: 0x85 (ADP)"},
        {"type": "P25_HDU", "algid": 0x85, "keyid": 0x0042},
    ])
    assert f.encrypted
    assert f.algorithm == "ADP-RC4"
    assert f.key_id == 0x0042


def test_p25_no_hdu_observed():
    f = probe_p25_frames([])
    assert f.encrypted is False
    assert "no P25" in " ".join(f.evidence)


# ---------------------------------------------------------------------------
# DMR
# ---------------------------------------------------------------------------

def test_dmr_pi_header_basic_privacy():
    f = probe_dmr_frames([
        {"type": "ENCRYPTION_EVIDENCE",
         "log_line": "PI header alg=0x21 keyid=0x03"},
    ])
    assert f.encrypted
    assert f.algorithm == "BASIC-PRIVACY"
    assert f.key_id == 0x03


def test_dmr_clear_when_no_pi():
    f = probe_dmr_frames([{"type": "DMR_VOICE"}])
    assert f.encrypted is False


def test_dmr_aes_line():
    f = probe_dmr_frames([
        {"type": "ENCRYPTION_EVIDENCE", "log_line": "Voice AES encrypted"},
    ])
    assert f.encrypted
    assert f.algorithm == "AES"


# ---------------------------------------------------------------------------
# TETRA
# ---------------------------------------------------------------------------

def test_tetra_mac_encr_security_class():
    f = probe_tetra_frames([
        {"type": "TETRA_MAC_ENCR", "security_class": 2,
         "log_line": "MAC-ENCR class 2"},
    ])
    assert f.encrypted
    assert f.algorithm_id == 2


def test_tetra_tea1_mention():
    f = probe_tetra_frames([
        {"type": "ENCRYPTION_EVIDENCE", "log_line": "cipher TEA1 enabled"},
    ])
    assert f.encrypted
    assert f.algorithm == "TEA1"


def test_tetra_clear():
    f = probe_tetra_frames([{"type": "TETRA_SYNC"}])
    assert f.encrypted is False


# ---------------------------------------------------------------------------
# dispatcher
# ---------------------------------------------------------------------------

def test_dispatcher_routes_by_label():
    f = probe_frames("p25_c4fm", [{"algid": 0x80}])
    assert f.encrypted is False
    f = probe_frames("tetra", [{"type": "TETRA_MAC_ENCR", "security_class": 1}])
    assert f.encrypted is True


def test_dispatcher_missing_label():
    f = probe_frames(None, [])
    assert f.encrypted is False
    assert "label missing" in " ".join(f.evidence)
