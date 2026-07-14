"""Transcription worker process.

Phase 1 scope: the process boundary and its logging/config bootstrap exist and are
proven to start without Qt. The lease, command loop, model manager and transcription
loop arrive in Phase 6, per WORKER_IPC_CONTRACT.md.

This module must never import PySide6 or anything under app.ui.
Enforced by tests/unit/test_architecture_layers.py.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app import config as config_mod
from app.logging_setup import setup_logging
from app.paths import DataPaths


def run_worker(data_dir: Path, instance_token: str) -> int:
    paths = DataPaths(root=data_dir)
    paths.ensure()

    cfg = config_mod.load(paths.config_file, paths.config_lastgood_file)

    setup_logging(
        paths.logs_dir,
        session_id=instance_token,
        role="worker",
        level=cfg.diagnostics.log_level,
        allow_transcript_bodies=cfg.privacy.log_transcript_bodies,
        keep_days=cfg.diagnostics.keep_log_days,
    )
    log = logging.getLogger("worker")
    log.info(
        "worker starting",
        extra={"instance_token": instance_token, "data_root": str(paths.root)},
    )

    # Phase 6 replaces this with WorkerLoop(...).run().
    log.info("worker runtime not implemented yet (arrives in Phase 6)")
    return 0
