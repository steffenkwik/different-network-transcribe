"""Attempt provenance key. It informs review but never itself queues a completed record."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CompatibilityInputs:
    engine_name: str
    engine_version: str
    model_name: str
    model_artifact_hash: str
    language: str
    task: str
    compute_type: str
    beam_size: int
    temperature: float
    vad_filter: bool
    condition_on_previous_text: bool
    source_sha256: str


def compatibility_key(inputs: CompatibilityInputs) -> str:
    payload = json.dumps(asdict(inputs), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
