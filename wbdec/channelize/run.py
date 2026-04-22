"""Stage-3 entry point: channelize detected events from a previous survey.

Takes the SplitSet (via ``cfg.capture``) and a survey.json, creates one
``ChannelExtractor`` per event, and drives them all with a single pass
over the streaming source. The channel extractors each hold their own
filter state, phase accumulator, and decimation carry-over, so a single
pass cleanly produces N SigMF channel files.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from ..capture.splits import SplitSet
from ..config import Config
from .extractor import ChannelExtractor, ExtractorConfig
from .grid import ChannelTarget, target_for_label
from .writer import ChannelMetaInputs, SigMFChannelWriter


def _load_survey(path: str) -> dict:
    with open(path, "r") as fh:
        return json.load(fh)


def run_channelize(cfg: Config, out_dir: Optional[str] = None,
                   survey_path: Optional[str] = None) -> Dict[str, dict]:
    """Run stage 3. Returns a dict ``{event_id: sigmf_meta_dict}``."""
    out_dir = out_dir or cfg.out_dir
    survey_path = survey_path or os.path.join(out_dir, "survey.json")
    if not os.path.exists(survey_path):
        raise FileNotFoundError(
            f"survey.json not found at {survey_path} — run `wbdec survey` first")
    survey = _load_survey(survey_path)
    channels_dir = os.path.join(out_dir, cfg.channelize.out_dir)
    os.makedirs(channels_dir, exist_ok=True)

    ss = SplitSet.discover(
        folder=cfg.capture.folder,
        sample_rate_hz=float(survey["sample_rate_hz"]),
        center_hz=float(survey["center_hz"]),
        fmt=cfg.capture.format,
    )

    # Build extractors + writers, keyed by event_id.
    writers: Dict[str, SigMFChannelWriter] = {}
    extractors: List[ChannelExtractor] = []
    for ev in survey["events"]:
        label = ev.get("label")
        target: ChannelTarget = target_for_label(label)
        meta_inputs = ChannelMetaInputs(
            event_id=ev["event_id"],
            label=label,
            label_confidence=float(ev.get("label_confidence", 0.0)),
            source_capture_meta=survey["capture_meta_path"],
            source_center_hz=ss.center_hz,
            source_sample_rate_hz=ss.sample_rate_hz,
            channel_center_hz=float(ev["center_hz"]),
            channel_bw_hz=target.channel_bw_hz * 2.0,
            out_sample_rate_hz=0.0,          # filled after extractor init
            t_start_s=float(ev["t_start_s"]),
            t_end_s=float(ev["t_end_s"]),
            demod_hint=target.demod_hint,
            apply_rrc=target.apply_rrc,
        )
        # Instantiate extractor first so we know the true output rate.
        ext_cfg = ExtractorConfig(
            event_id=ev["event_id"],
            center_offset_hz=float(ev["center_hz"]) - ss.center_hz,
            source_rate_hz=ss.sample_rate_hz,
            target=target,
            t_start_s=float(ev["t_start_s"]),
            t_end_s=float(ev["t_end_s"]),
        )
        writer = SigMFChannelWriter(channels_dir, ev["event_id"], meta_inputs)
        writers[ev["event_id"]] = writer

        def _sink(w: SigMFChannelWriter):
            def _cb(samples):
                w.write(samples)
            return _cb

        extractor = ChannelExtractor(ext_cfg, on_samples=_sink(writer))
        # Patch out_sample_rate into the meta inputs so the meta file is correct.
        writer.meta_inputs.out_sample_rate_hz = extractor.out_rate_hz
        extractors.append(extractor)

    # 2. Single-pass stream.
    fs = ss.sample_rate_hz
    for _, stream_offset, chunk in ss.iter_chunks(cfg.capture.chunk_samples):
        chunk_start_t_s = stream_offset / fs
        chunk_end_t_s = chunk_start_t_s + chunk.size / fs
        for ext in extractors:
            if ext.is_active_for_chunk(chunk_start_t_s, chunk_end_t_s):
                ext.push_chunk(chunk, chunk_start_t_s)

    # 3. Close writers.
    result: Dict[str, dict] = {}
    for eid, w in writers.items():
        result[eid] = w.close()
    return result
