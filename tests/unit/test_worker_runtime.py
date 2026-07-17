"""Synthetic worker lifecycle tests: leases, one model load, failure isolation, recovery."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest

from app.database.connection import open_connection
from app.database.migrations import MigrationRunner
from app.database.worker_repository import WorkerRepository
from app.services.worker_status import progress_percent
from app.transcription.engine import EngineResult
from worker.runtime import WorkerLoop, WorkerStep

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.worker]


class FakeEngine:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.load_count = 0
        self.transcribe_count = 0
        self.fail_first = fail_first

    def load(self) -> None:
        self.load_count += 1

    def transcribe(self, path: Path) -> EngineResult:
        self.transcribe_count += 1
        if self.fail_first and self.transcribe_count == 1:
            raise ValueError("synthetic corrupt input")
        return EngineResult(
            raw_transcript=f"synthetic {path.name}", normalized_transcript=f"synthetic {path.name}"
        )


class SlowEngine(FakeEngine):
    def transcribe(self, path: Path) -> EngineResult:
        time.sleep(1.1)
        return super().transcribe(path)


@pytest.fixture
def database(tmp_path: Path):
    path = tmp_path / "data" / "Database" / "test.sqlite3"
    MigrationRunner(path, REPO_ROOT / "migrations", tmp_path / "data" / "Backups").migrate()
    connection = open_connection(path)
    try:
        source = tmp_path / "source"
        source.mkdir()
        root = connection.execute(
            "INSERT INTO source_roots(kind, original_path, normalized_path, created_at) VALUES ('audio', ?, ?, 't')",
            (str(tmp_path / "source"), str(tmp_path / "source").casefold()),
        ).lastrowid
        for index in range(2):
            content = f"synthetic-source-{index}".encode()
            (source / f"voice-{index}.opus").write_bytes(content)
            audio = connection.execute(
                """INSERT INTO audio_files(stable_file_id, source_root_id, current_relative_path, basename,
                   normalized_basename, extension, size_bytes, first_discovered_at, last_seen_at, current_state,
                   created_at, updated_at) VALUES (?, ?, ?, ?, ?, '.opus', ?, 't', 't', 'queued', 't', 't')""",
                (
                    f"audio-{index}",
                    root,
                    f"voice-{index}.opus",
                    f"voice-{index}.opus",
                    f"voice-{index}.opus",
                    len(content),
                ),
            ).lastrowid
            version = connection.execute(
                "INSERT INTO audio_source_versions(audio_file_id, size_bytes, sha256, discovered_at) VALUES (?, ?, ?, 't')",
                (audio, len(content), hashlib.sha256(content).hexdigest()),
            ).lastrowid
            connection.execute(
                "UPDATE audio_files SET current_source_version_id = ? WHERE id = ?",
                (version, audio),
            )
        yield path, connection
    finally:
        connection.close()


def test_model_loads_once_and_completes_each_file(database) -> None:
    path, connection = database
    engine = FakeEngine()
    worker = WorkerLoop(path, "session-a", engine)
    worker.start()
    assert worker.run_one() is WorkerStep.PROCESSED
    assert worker.run_one() is WorkerStep.PROCESSED
    assert worker.run_one() is WorkerStep.IDLE
    assert engine.load_count == 1
    assert engine.transcribe_count == 2
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM transcription_attempts WHERE state = 'completed'"
        ).fetchone()[0]
        == 2
    )
    assert connection.execute(
        "SELECT COUNT(*) FROM transcript_fts_map WHERE audio_file_id IN (SELECT id FROM audio_files)"
    ).fetchone()[0] == 2
    assert connection.execute(
        "SELECT COUNT(*) FROM transcript_fts WHERE transcript_fts MATCH 'synthetic'"
    ).fetchone()[0] == 2
    worker.close()


def test_attempt_keeps_selected_model_settings_and_compatibility_provenance(database) -> None:
    path, connection = database
    worker = WorkerLoop(
        path,
        "medium-provenance",
        FakeEngine(),
        model_name="medium",
        model_hash="model-hash",
        language="auto",
        attempt_settings={
            "language": "auto",
            "task": "transcribe",
            "compute_type": "int8",
            "beam_size": 5,
            "temperature": 0.0,
            "vad_filter": True,
            "condition_on_previous_text": False,
        },
    )
    worker.start()
    assert worker.run_one() is WorkerStep.PROCESSED
    row = connection.execute(
        "SELECT model_name, model_hash, language, settings_json, compat_key FROM transcription_attempts"
    ).fetchone()
    assert tuple(row[:3]) == ("medium", "model-hash", "auto")
    assert json.loads(row[3])["beam_size"] == 5
    assert len(str(row[4])) == 64
    worker.close()


@pytest.mark.acceptance
def test_restart_skips_completed_sources_with_zero_new_inference(database) -> None:
    """The addendum's no-repeat proof: a second run must not call inference."""
    path, connection = database
    first_engine = FakeEngine()
    first = WorkerLoop(path, "first-run", first_engine)
    first.start()
    while first.run_one() is WorkerStep.PROCESSED:
        pass
    first.close()
    attempts_before = connection.execute("SELECT COUNT(*) FROM transcription_attempts").fetchone()[0]

    second_engine = FakeEngine()
    second = WorkerLoop(path, "second-run", second_engine)
    second.start()
    assert second.run_one() is WorkerStep.IDLE
    assert second_engine.transcribe_count == 0
    assert connection.execute("SELECT COUNT(*) FROM transcription_attempts").fetchone()[0] == attempts_before
    assert connection.execute(
        "SELECT COUNT(*) FROM processing_events WHERE event_type='skipped_complete'"
    ).fetchone()[0] == 2
    second.close()


@pytest.mark.acceptance
def test_explicit_reprocess_preserves_old_attempt_and_runs_only_selected_file(database) -> None:
    path, connection = database
    first = WorkerLoop(path, "baseline", FakeEngine())
    first.start()
    while first.run_one() is WorkerStep.PROCESSED:
        pass
    first.close()
    selected_id = int(
        connection.execute("SELECT id FROM audio_files ORDER BY id LIMIT 1").fetchone()[0]
    )

    engine = FakeEngine()
    second = WorkerLoop(path, "explicit-reprocess", engine)
    session_id = second.start()
    command_id = WorkerRepository(connection).enqueue_command(
        session_id, "reprocess_selected", {"audio_file_ids": [selected_id]}
    )
    assert second.run_one() is WorkerStep.COMMAND_HANDLED
    assert second.run_one() is WorkerStep.PROCESSED
    assert engine.transcribe_count == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM transcription_attempts WHERE audio_file_id = ?", (selected_id,)
    ).fetchone()[0] == 2
    assert connection.execute(
        "SELECT COUNT(*) FROM transcription_attempts"
    ).fetchone()[0] == 3
    assert connection.execute(
        "SELECT result FROM worker_commands WHERE id = ?", (command_id,)
    ).fetchone()[0] == "requeued:1"
    assert connection.execute(
        "SELECT COUNT(*) FROM processing_events WHERE event_type='explicit_reprocess_requested'"
    ).fetchone()[0] == 1
    second.close()


def test_bad_file_fails_but_next_file_continues(database) -> None:
    path, connection = database
    worker = WorkerLoop(path, "session-b", FakeEngine(fail_first=True))
    worker.start()
    assert worker.run_one() is WorkerStep.PROCESSED
    assert worker.run_one() is WorkerStep.PROCESSED
    states = [
        row[0] for row in connection.execute("SELECT state FROM transcription_attempts ORDER BY id")
    ]
    assert states == ["failed", "completed"]
    worker.close()


def test_explicit_retry_failed_requeues_only_failed_records(database) -> None:
    path, connection = database
    first = WorkerLoop(path, "fail-then-retry", FakeEngine(fail_first=True))
    first.start()
    assert first.run_one() is WorkerStep.PROCESSED
    first.close()
    failed_id = int(
        connection.execute("SELECT id FROM audio_files WHERE current_state = 'failed'").fetchone()[0]
    )
    second = WorkerLoop(path, "retry", FakeEngine())
    retry_session = second.start()
    command = WorkerRepository(connection).enqueue_command(retry_session, "retry_failed")
    assert second.run_one() is WorkerStep.COMMAND_HANDLED
    assert second.run_one() is WorkerStep.PROCESSED
    assert connection.execute(
        "SELECT COUNT(*) FROM transcription_attempts WHERE audio_file_id = ?", (failed_id,)
    ).fetchone()[0] == 2
    assert connection.execute("SELECT result FROM worker_commands WHERE id = ?", (command,)).fetchone()[0] == "requeued_failed:1"
    second.close()


def test_active_root_guard_never_claims_queued_audio_from_another_folder(database) -> None:
    """A user testing one folder must never start an old, wider queue by accident."""
    path, connection = database
    test_root = path.parents[2] / "source"
    old_root = path.parents[2] / "old-source"
    old_root.mkdir()
    content = b"must-not-be-claimed"
    (old_root / "old.opus").write_bytes(content)
    root_id = connection.execute(
        "INSERT INTO source_roots(kind, original_path, normalized_path, created_at) VALUES ('audio', ?, ?, 't')",
        (str(old_root), str(old_root).casefold()),
    ).lastrowid
    audio_id = connection.execute(
        """INSERT INTO audio_files(stable_file_id, source_root_id, current_relative_path, basename,
           normalized_basename, extension, size_bytes, first_discovered_at, last_seen_at, current_state,
           created_at, updated_at) VALUES ('old-audio', ?, 'old.opus', 'old.opus', 'old.opus', '.opus',
           ?, 't', 't', 'queued', 't', 't')""",
        (root_id, len(content)),
    ).lastrowid
    version_id = connection.execute(
        "INSERT INTO audio_source_versions(audio_file_id, size_bytes, sha256, discovered_at) VALUES (?, ?, ?, 't')",
        (audio_id, len(content), hashlib.sha256(content).hexdigest()),
    ).lastrowid
    connection.execute("UPDATE audio_files SET current_source_version_id = ? WHERE id = ?", (version_id, audio_id))

    engine = FakeEngine()
    worker = WorkerLoop(path, "active-root", engine, active_root=test_root)
    worker.start()
    while worker.run_one() is WorkerStep.PROCESSED:
        pass
    worker.close()

    assert engine.transcribe_count == 2
    assert connection.execute("SELECT current_state FROM audio_files WHERE id = ?", (audio_id,)).fetchone()[0] == "queued"


def test_duplicate_worker_lease_is_blocked(database) -> None:
    path, _ = database
    first = WorkerLoop(path, "session-c", FakeEngine())
    first.start()
    second = WorkerLoop(path, "session-d", FakeEngine())
    with pytest.raises(RuntimeError, match="sudah berjalan"):
        second.start()
    first.close()
    second.connection.close()


def test_safe_stop_releases_lease_without_claiming_new_work(database) -> None:
    path, connection = database
    worker = WorkerLoop(path, "session-e", FakeEngine())
    session_id = worker.start()
    WorkerRepository(connection).enqueue_command(session_id, "safe_stop")
    assert worker.run_one() is WorkerStep.STOPPED
    assert (
        connection.execute(
            "SELECT state FROM worker_sessions WHERE id = ?", (session_id,)
        ).fetchone()[0]
        == "stopped"
    )
    assert connection.execute("SELECT COUNT(*) FROM transcription_attempts").fetchone()[0] == 0
    worker.connection.close()


def test_pause_then_resume_does_not_claim_work_while_paused(database) -> None:
    path, connection = database
    status_file = path.parent / "worker-status.json"
    worker = WorkerLoop(path, "session-pause", FakeEngine(), status_file=status_file)
    session_id = worker.start()
    repository = WorkerRepository(connection)
    repository.enqueue_command(session_id, "pause")
    assert worker.run_one() is WorkerStep.PAUSED
    assert worker.paused is True
    assert json.loads(status_file.read_text(encoding="utf-8"))["state"] == "paused"
    assert connection.execute("SELECT COUNT(*) FROM transcription_attempts").fetchone()[0] == 0
    # A paused loop must keep reporting PAUSED rather than draining the queue.
    assert worker.run_one() is WorkerStep.PAUSED
    assert connection.execute("SELECT COUNT(*) FROM transcription_attempts").fetchone()[0] == 0
    repository.enqueue_command(session_id, "resume")
    assert worker.run_one() is WorkerStep.COMMAND_HANDLED
    assert worker.paused is False
    assert worker.run_one() is WorkerStep.PROCESSED
    worker.close()


def test_resume_command_never_ends_the_worker_process(database) -> None:
    """P0-1 regression: the driver loop used to exit on the resume command.

    A resume reports COMMAND_HANDLED, which must keep the driver running so the
    remaining queue is transcribed by the same already-loaded model.
    """
    from worker.main import _drive

    path, connection = database
    engine = FakeEngine()
    worker = WorkerLoop(path, "session-resume-drive", engine)
    session_id = worker.start()
    repository = WorkerRepository(connection)
    repository.enqueue_command(session_id, "pause")
    repository.enqueue_command(session_id, "resume")

    _drive(worker, idle_exit_seconds=0.0, sleep=lambda _: None)

    assert engine.transcribe_count == 2
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM audio_files WHERE current_state = 'completed_preferred'"
        ).fetchone()[0]
        == 2
    )
    worker.close()


def test_idle_worker_stays_alive_long_enough_to_receive_a_late_command(database) -> None:
    """P0-1 regression: reprocess after the queue drains needs a live worker."""
    from worker.main import _drive

    path, connection = database
    engine = FakeEngine()
    worker = WorkerLoop(path, "session-idle-window", engine)
    session_id = worker.start()
    repository = WorkerRepository(connection)
    selected_id = int(
        connection.execute("SELECT id FROM audio_files ORDER BY id LIMIT 1").fetchone()[0]
    )
    ticks: list[float] = [0.0]
    enqueued: list[bool] = [False]

    def clock() -> float:
        return ticks[0]

    def sleep(seconds: float) -> None:
        ticks[0] += seconds
        # Simulate the user pressing "reprocess" a few seconds after the queue drained.
        if ticks[0] >= 3.0 and not enqueued[0]:
            enqueued[0] = True
            repository.enqueue_command(
                session_id, "reprocess_selected", {"audio_file_ids": [selected_id]}
            )

    _drive(worker, idle_exit_seconds=30.0, sleep=sleep, clock=clock)

    # Two initial files plus the explicitly reprocessed one.
    assert engine.transcribe_count == 3
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM transcription_attempts WHERE audio_file_id = ?", (selected_id,)
        ).fetchone()[0]
        == 2
    )
    worker.close()


def test_status_file_reports_session_progress_not_all_time_history(database) -> None:
    """P0-3 regression: a new session must not inherit yesterday's completions."""
    path, connection = database
    status_file = path.parent / "worker-status.json"

    first = WorkerLoop(path, "history", FakeEngine(), status_file=status_file)
    first.start()
    while first.run_one() is WorkerStep.PROCESSED:
        pass
    first.close()

    # Give the archive one more untranscribed file, then start a fresh session.
    source = path.parents[2] / "source"
    content = b"synthetic-source-new"
    (source / "voice-new.opus").write_bytes(content)
    root_id = int(connection.execute("SELECT id FROM source_roots LIMIT 1").fetchone()[0])
    audio_id = connection.execute(
        """INSERT INTO audio_files(stable_file_id, source_root_id, current_relative_path, basename,
           normalized_basename, extension, size_bytes, first_discovered_at, last_seen_at,
           current_state, created_at, updated_at)
           VALUES ('audio-new', ?, 'voice-new.opus', 'voice-new.opus', 'voice-new.opus', '.opus',
           ?, 't', 't', 'discovered', 't', 't')""",
        (root_id, len(content)),
    ).lastrowid
    version_id = connection.execute(
        "INSERT INTO audio_source_versions(audio_file_id, size_bytes, sha256, discovered_at) VALUES (?, ?, ?, 't')",
        (audio_id, len(content), hashlib.sha256(content).hexdigest()),
    ).lastrowid
    connection.execute(
        "UPDATE audio_files SET current_source_version_id = ? WHERE id = ?", (version_id, audio_id)
    )

    second = WorkerLoop(path, "fresh-session", FakeEngine(), status_file=status_file)
    second.start()
    status = json.loads(status_file.read_text(encoding="utf-8"))
    assert status["schema"] == 2
    # One file is claimable; the two already-transcribed ones must not inflate it.
    assert status["session"]["total"] == 1
    assert status["session"]["done"] == 0
    assert progress_percent(status) == 0
    assert status["counts"]["completed"] == 2

    assert second.run_one() is WorkerStep.PROCESSED
    status = json.loads(status_file.read_text(encoding="utf-8"))
    assert status["session"]["done"] == 1
    assert progress_percent(status) == 100
    second.close()


def test_requeued_work_widens_the_session_denominator(database) -> None:
    path, connection = database
    status_file = path.parent / "worker-status.json"
    worker = WorkerLoop(path, "requeue-total", FakeEngine(), status_file=status_file)
    session_id = worker.start()
    while worker.run_one() is WorkerStep.PROCESSED:
        pass
    assert json.loads(status_file.read_text(encoding="utf-8"))["session"]["total"] == 2

    selected_id = int(connection.execute("SELECT id FROM audio_files ORDER BY id LIMIT 1").fetchone()[0])
    WorkerRepository(connection).enqueue_command(
        session_id, "reprocess_selected", {"audio_file_ids": [selected_id]}
    )
    assert worker.run_one() is WorkerStep.COMMAND_HANDLED
    status = json.loads(status_file.read_text(encoding="utf-8"))
    assert status["session"]["total"] == 3
    assert progress_percent(status) == 67
    assert worker.run_one() is WorkerStep.PROCESSED
    assert progress_percent(json.loads(status_file.read_text(encoding="utf-8"))) == 100
    worker.close()


def test_finished_status_is_written_when_the_queue_drains(database) -> None:
    from worker.main import _drive

    path, _ = database
    status_file = path.parent / "worker-status.json"
    worker = WorkerLoop(path, "drain", FakeEngine(), status_file=status_file)
    worker.start()
    _drive(worker, idle_exit_seconds=0.0, sleep=lambda _: None)
    status = json.loads(status_file.read_text(encoding="utf-8"))
    assert status["state"] == "finished"
    assert status["session"]["done"] == 2
    assert progress_percent(status) == 100
    worker.close()


def test_heartbeat_stays_fresh_while_local_inference_is_running(database) -> None:
    path, connection = database
    seen: list[str] = []

    class ObservingEngine(SlowEngine):
        def transcribe(self, source: Path) -> EngineResult:
            time.sleep(1.0)
            reader = open_connection(path, read_only=True)
            try:
                seen.append(str(reader.execute("SELECT heartbeat_at FROM worker_sessions").fetchone()[0]))
            finally:
                reader.close()
            return super().transcribe(source)

    worker = WorkerLoop(path, "heartbeat", ObservingEngine(), heartbeat_interval_seconds=0.05)
    session_id = worker.start()
    before = str(
        connection.execute("SELECT heartbeat_at FROM worker_sessions WHERE id = ?", (session_id,)).fetchone()[0]
    )
    assert worker.run_one() is WorkerStep.PROCESSED
    worker.close()
    assert seen and seen[0] > before


def test_stale_processing_attempt_is_interrupted_and_only_that_audio_requeued(database) -> None:
    _, connection = database
    repository = WorkerRepository(connection)
    session_id = repository.acquire_lease("stale", 1)
    claim = repository.claim_next(session_id)
    assert claim is not None
    connection.execute(
        "UPDATE worker_sessions SET heartbeat_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
        (session_id,),
    )
    assert repository.recover_stale_sessions() == 1
    assert (
        connection.execute(
            "SELECT state FROM transcription_attempts WHERE id = ?", (claim["attempt_id"],)
        ).fetchone()[0]
        == "interrupted"
    )
    assert (
        connection.execute(
            "SELECT current_state FROM audio_files WHERE id = ?", (claim["id"],)
        ).fetchone()[0]
        == "queued"
    )


def test_corrupt_model_is_reported_as_corrupt_and_marked_suspect(tmp_path: Path) -> None:
    """P0-6 regression: weights that exist but cannot load said only 'gagal dimulai'."""
    from app import config as config_mod
    from app.config import AppConfig
    from app.paths import DataPaths
    from app.transcription.model_registry import MODELS, ModelRegistry
    from worker.main import run_worker

    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    source = tmp_path / "source"
    source.mkdir()
    config = AppConfig()
    config.paths.audio_roots = [str(source)]
    config_mod.save(config, paths.config_file, paths.config_lastgood_file)

    # Files exist and are non-empty, so the cheap check passes, but the bytes are
    # not a real CTranslate2 model.
    model_dir = paths.models_dir / "small"
    model_dir.mkdir(parents=True)
    for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.json"):
        (model_dir / name).write_bytes(b"corrupted-not-a-model")
    registry = ModelRegistry(paths.models_dir)
    registry._write_registry(
        MODELS["small"],
        {"model.bin": {"size": 21, "sha256": "deadbeef"}},
        "download",
    )
    assert registry.read()["models"]["small"]["verification_state"] == "verified"

    assert run_worker(paths.root, "corrupt-model") == 3
    status = json.loads(paths.worker_status_file.read_text(encoding="utf-8"))
    assert status["state"] == "failed"
    assert "Unduh ulang model" in status["last_safe_message"]
    assert registry.read()["models"]["small"]["verification_state"] == "suspect"
    # A model that never loaded must not leave a worker session behind.
    connection = open_connection(paths.database_file)
    try:
        assert connection.execute("SELECT COUNT(*) FROM worker_sessions").fetchone()[0] == 0
    finally:
        connection.close()


def test_worker_entrypoint_returns_safe_missing_model_status(tmp_path: Path) -> None:
    from app import config as config_mod
    from app.config import AppConfig
    from app.paths import DataPaths
    from worker.main import run_worker

    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    assert run_worker(paths.root, "no-root") == 4

    source = tmp_path / "source"
    source.mkdir()
    config = AppConfig()
    config.paths.audio_roots = [str(source)]
    config_mod.save(config, paths.config_file, paths.config_lastgood_file)

    assert run_worker(paths.root, "missing-model") == 3
    status = json.loads(paths.worker_status_file.read_text(encoding="utf-8"))
    assert status["state"] == "failed"
    assert status["last_safe_message"] == "Model tidak ditemukan atau rusak."
