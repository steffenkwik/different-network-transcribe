"""Transcription worker process.

Phase 1 scope: the process boundary and its logging/config bootstrap exist and are
proven to start without Qt. The lease, command loop, model manager and transcription
loop arrive in Phase 6, per WORKER_IPC_CONTRACT.md.

This module must never import PySide6 or anything under app.ui.
Enforced by tests/unit/test_architecture_layers.py.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from app import config as config_mod
from app.database.migrations import MigrationRunner
from app.logging_setup import setup_logging
from app.paths import DataPaths
from app.runtime import bundled_path
from app.transcription.engine import FasterWhisperEngine
from app.transcription.model_registry import ModelError, ModelRegistry
from worker.runtime import WorkerLoop


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

    MigrationRunner(
        paths.database_file,
        bundled_path("migrations"),
        paths.backups_dir,
    ).migrate()
    model_directory = paths.models_dir / cfg.transcription.default_model
    try:
        ModelRegistry(paths.models_dir).verify(cfg.transcription.default_model, full_hash=False)
    except ModelError:
        log.error("model missing", extra={"model": cfg.transcription.default_model})
        return 3
    worker = WorkerLoop(
        paths.database_file,
        instance_token,
        FasterWhisperEngine(model_directory, language=cfg.transcription.language),
    )
    try:
        worker.start()
        while not worker.stopped:
            did_work = worker.run_one()
            if worker.stopped or (not did_work and not worker.paused):
                break
            if not did_work:
                time.sleep(1)
    except Exception:
        log.exception("worker failed")
        if worker.session_id is not None:
            worker.repository.stop(worker.session_id, failed=True)
        return 1
    finally:
        worker.close()
    return 0
