"""Top-level pipeline: ingest → detect → classify → extract → decode → report."""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any, Dict, List

import numpy as np

from ..config import WidebandConfig
from ..ingest import ContiguousStream
from ..detect import (
    SignalEvent,
    stream_frames,
    ca_cfar,
    group_peaks,
    EventTracker,
)
from ..detect.psd import psd_freqs
from ..classify import classify_event
from ..extract import extract_channel, fm_discriminator, resample_to
from ..decode import (
    decode_with_dsd,
    decode_with_dsd_subprocess,
    decode_with_tetra_rx,
    decode_dpmr_stub,
)
from ..crypto import (
    EncryptionReport,
    probe_p25_encryption,
    probe_tetra_encryption,
)
from ..io import write_wav_int16, write_json, write_spectrogram_png


def _detect_events(cfg: WidebandConfig, folder_iq: ContiguousStream
                   ) -> tuple[List[SignalEvent], np.ndarray, np.ndarray]:
    nperseg = cfg.detect.nperseg
    nav = cfg.detect.nav
    sample_rate = folder_iq.sample_rate
    freqs = psd_freqs(nperseg, sample_rate, folder_iq.center_hz)
    frame_period = (nperseg * nav) / sample_rate
    tracker = EventTracker(
        frame_period_s=frame_period,
        min_persist_frames=cfg.detect.min_persist_frames,
        max_absent_frames=cfg.detect.max_absent_frames,
    )
    running_avg = np.zeros(nperseg, dtype=np.float64)
    frame_count = 0
    min_bins = max(1, int(cfg.detect.min_bw_hz * nperseg / sample_rate))
    max_bins = max(min_bins, int(cfg.detect.max_bw_hz * nperseg / sample_rate))
    for idx, psd in stream_frames(iter(folder_iq), nperseg, nav):
        running_avg += psd
        frame_count += 1
        mask = ca_cfar(psd, cfg.detect.cfar_guard, cfg.detect.cfar_train,
                       cfg.detect.cfar_pfa)
        groups = group_peaks(mask, freqs, psd,
                             min_bins=min_bins, max_bins=max_bins)
        detections = []
        for lo, hi, center, bw in groups:
            peak = float(psd[lo: hi + 1].max())
            noise_band = np.concatenate([
                psd[max(0, lo - cfg.detect.cfar_train): lo],
                psd[hi + 1: hi + 1 + cfg.detect.cfar_train],
            ])
            noise = float(noise_band.mean()) if noise_band.size else 1e-20
            detections.append((center, bw, peak, noise))
        tracker.update(idx, detections)
    tracker.flush()
    events = tracker.events()
    avg = (running_avg / max(frame_count, 1)).astype(np.float32)
    return events, avg, freqs


def _process_event(cfg: WidebandConfig, event: SignalEvent,
                   stream_iq: np.ndarray, sample_rate: float,
                   center_hz_abs: float) -> Dict[str, Any]:
    offset_hz = event.center_hz - center_hz_abs
    bb, bb_rate = extract_channel(
        stream_iq, sample_rate, offset_hz,
        channel_bw_hz=max(event.bw_hz * 1.4, 12_500.0),
        out_sample_rate=48_000.0,
    )
    demod = fm_discriminator(bb, gain=1.6)
    label, conf, features = classify_event(bb, bb_rate, demod)
    event.label = label
    event.label_confidence = conf

    out_dir = os.path.join(cfg.output.out_dir, f"ch_{int(event.center_hz):d}")
    os.makedirs(out_dir, exist_ok=True)

    entry: Dict[str, Any] = {
        "event": event.to_dict(),
        "features": asdict(features),
        "baseband_rate_hz": float(bb_rate),
        "out_dir": out_dir,
        "decode": {"mode": label, "ok": False},
        "encryption": None,
    }

    if label in ("p25_c4fm", "dmr") and (
        (label == "p25_c4fm" and cfg.decode.enable_p25)
        or (label == "dmr" and cfg.decode.enable_dmr)
    ):
        # Resample discriminator from bb_rate to 48 kHz for the DSD block.
        demod_48k = resample_to(demod.astype(np.float32), bb_rate, 48_000.0)
        backend = (cfg.decode.dsd_backend or "gr").lower()
        if backend == "subprocess":
            sres = decode_with_dsd_subprocess(
                demod_48k, label, out_dir,
                binary=cfg.decode.dsd_binary,
                flavor=cfg.decode.dsd_flavor,
                extra_args=list(cfg.decode.dsd_extra_args or []),
            )
            entry["decode"] = {
                "mode": sres.mode,
                "ok": sres.ok,
                "backend": "subprocess",
                "flavor": sres.flavor,
                "error": sres.error,
            }
            if sres.wav_path:
                entry["decode"]["wav"] = sres.wav_path
            if cfg.crypto.detect and label == "p25_c4fm":
                state = probe_p25_encryption(sres.algid, sres.keyid)
                if sres.encryption_evidence:
                    state.evidence.extend(sres.encryption_evidence)
                entry["encryption"] = EncryptionReport(state=state).to_dict()
        else:
            res = decode_with_dsd(demod_48k, label)
            entry["decode"] = {
                "mode": res.mode,
                "ok": res.ok,
                "backend": "gr",
                "error": res.error,
            }
            if cfg.output.write_wav and res.pcm_8k is not None:
                wav_path = os.path.join(out_dir, "voice_8k.wav")
                write_wav_int16(wav_path, res.pcm_8k, 8000)
                entry["decode"]["wav"] = wav_path
            if cfg.crypto.detect and label == "p25_c4fm":
                state = probe_p25_encryption(res.algid, res.keyid)
                entry["encryption"] = EncryptionReport(state=state).to_dict()
    elif label == "tetra" and cfg.decode.enable_tetra:
        res = decode_with_tetra_rx(bb, bb_rate, out_dir,
                                   tetra_rx_bin=cfg.decode.tetra_rx_binary)
        entry["decode"] = {"mode": "tetra", "ok": res.ok, "error": res.error,
                           "pcm": res.pcm_path}
        if cfg.crypto.detect:
            state = probe_tetra_encryption(res.raw_log.splitlines())
            entry["encryption"] = EncryptionReport(state=state).to_dict()
    elif label == "dpmr":
        # dsd-fme supports dPMR (-fm); route to the subprocess runner when the
        # selected flavor has a mapping, else fall back to the detect-only stub.
        from ..decode.dsdplus_runner import _MODE_TO_FLAG
        backend = (cfg.decode.dsd_backend or "gr").lower()
        if (backend == "subprocess"
                and cfg.decode.dsd_flavor in _MODE_TO_FLAG
                and "dpmr" in _MODE_TO_FLAG[cfg.decode.dsd_flavor]):
            demod_48k = resample_to(demod.astype(np.float32), bb_rate, 48_000.0)
            sres = decode_with_dsd_subprocess(
                demod_48k, "dpmr", out_dir,
                binary=cfg.decode.dsd_binary,
                flavor=cfg.decode.dsd_flavor,
                extra_args=list(cfg.decode.dsd_extra_args or []),
            )
            entry["decode"] = {
                "mode": "dpmr",
                "ok": sres.ok,
                "backend": "subprocess",
                "flavor": sres.flavor,
                "error": sres.error,
            }
            if sres.wav_path:
                entry["decode"]["wav"] = sres.wav_path
        else:
            res = decode_dpmr_stub(demod)
            entry["decode"] = {"mode": "dpmr", "ok": res.ok, "note": res.note}
    else:
        entry["decode"] = {"mode": label, "ok": False,
                           "note": "decoder disabled or classification unknown"}
    return entry


def run_job(cfg: WidebandConfig) -> Dict[str, Any]:
    """Execute the full pipeline synchronously. Returns run-level report dict."""
    os.makedirs(cfg.output.out_dir, exist_ok=True)

    # Pass 1: detection needs to iterate blocks. We buffer the stream into
    # memory because each detected event needs a time-sliced view afterwards.
    # For multi-GB captures, replace this with a two-pass on-disk strategy.
    stream = ContiguousStream(
        folder=cfg.ingest.folder,
        sample_rate=cfg.ingest.sample_rate,
        center_hz=cfg.ingest.center_hz,
        format_hint=cfg.ingest.format,
        block_size=cfg.ingest.block_size,
    )
    blocks: List[np.ndarray] = []
    for blk in stream:
        blocks.append(blk)
    if not blocks:
        raise RuntimeError("ingest produced no samples")
    full = np.concatenate(blocks)
    sample_rate = stream.sample_rate
    center_hz_abs = stream.center_hz

    # Detection works on an iterator over the buffered stream.
    det_stream = ContiguousStream(
        folder=cfg.ingest.folder,
        sample_rate=cfg.ingest.sample_rate,
        center_hz=cfg.ingest.center_hz,
        format_hint=cfg.ingest.format,
        block_size=cfg.ingest.block_size,
    )
    events, avg_psd, freqs = _detect_events(cfg, det_stream)

    if cfg.output.write_spectrogram_png:
        db = 10.0 * np.log10(np.maximum(avg_psd, 1e-20))
        write_spectrogram_png(
            os.path.join(cfg.output.out_dir, "psd.png"),
            db, freqs, title=f"Wideband PSD ({len(events)} events)",
        )

    per_event: List[Dict[str, Any]] = []
    for ev in events:
        per_event.append(_process_event(cfg, ev, full, sample_rate, center_hz_abs))

    report = {
        "config": cfg.to_json(),
        "sample_rate_hz": float(sample_rate),
        "center_hz": float(center_hz_abs),
        "num_events": len(events),
        "events": per_event,
        "stream_gaps": [
            {"after_file": g.after_file, "dropped_samples": g.dropped_samples}
            for g in stream.gaps
        ],
    }
    write_json(os.path.join(cfg.output.out_dir, "report.json"), report)
    return report
