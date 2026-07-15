"""Synthetic worker lifecycle tests: leases, one model load, failure isolation, recovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.database.connection import open_connection
from app.database.migrations import MigrationRunner
from app.database.worker_repository import WorkerRepository
from app.transcription.engine import EngineResult
from worker.runtime import WorkerLoop

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


@pytest.fixture
def database(tmp_path: Path):
    path = tmp_path / "data" / "Database" / "test.sqlite3"
    MigrationRunner(path, REPO_ROOT / "migrations", tmp_path / "data" / "Backups").migrate()
    connection = open_connection(path)
    try:
        root = connection.execute(
            "INSERT INTO source_roots(kind, original_path, normalized_path, created_at) VALUES ('audio', ?, ?, 't')",
            (str(tmp_path / "source"), str(tmp_path / "source").casefold()),
        ).lastrowid
        for index in range(2):
            audio = connection.execute(
                """INSERT INTO audio_files(stable_file_id, source_root_id, current_relative_path, basename,
                   normalized_basename, extension, size_bytes, first_discovered_at, last_seen_at, current_state,
                   created_at, updated_at) VALUES (?, ?, ?, ?, ?, '.opus', 1, 't', 't', 'queued', 't', 't')""",
                (
                    f"audio-{index}",
                    root,
                    f"voice-{index}.opus",
                    f"voice-{index}.opus",
                    f"voice-{index}.opus",
                ),
            ).lastrowid
            version = connection.execute(
                "INSERT INTO audio_source_versions(audio_file_id, size_bytes, sha256, discovered_at) VALUES (?, 1, ?, 't')",
                (audio, f"hash-{index}"),
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
    assert worker.run_one() is True
    assert worker.run_one() is True
    assert worker.run_one() is False
    assert engine.load_count == 1
    assert engine.transcribe_count == 2
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM transcription_attempts WHERE state = 'completed'"
        ).fetchone()[0]
        == 2
    )
    worker.close()


def test_bad_file_fails_but_next_file_continues(database) -> None:
    path, connection = database
    worker = WorkerLoop(path, "session-b", FakeEngine(fail_first=True))
    worker.start()
    assert worker.run_one() is True
    assert worker.run_one() is True
    states = [
        row[0] for row in connection.execute("SELECT state FROM transcription_attempts ORDER BY id")
    ]
    assert states == ["failed", "completed"]
    worker.close()


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
    assert worker.run_one() is False
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
    worker = WorkerLoop(path, "session-pause", FakeEngine())
    session_id = worker.start()
    repository = WorkerRepository(connection)
    repository.enqueue_command(session_id, "pause")
    assert worker.run_one() is False
    assert worker.paused is True
    assert connection.execute("SELECT COUNT(*) FROM transcription_attempts").fetchone()[0] == 0
    repository.enqueue_command(session_id, "resume")
    assert worker.run_one() is False
    assert worker.paused is False
    assert worker.run_one() is True
    worker.close()


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


def test_worker_entrypoint_returns_safe_missing_model_status(tmp_path: Path) -> None:
    from worker.main import run_worker

    assert run_worker(tmp_path / "data", "missing-model") == 3
