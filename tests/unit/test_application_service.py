"""Application use cases exercise services without importing the Qt layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.database.connection import open_connection
from app.paths import DataPaths
from app.services.application_service import ApplicationService

pytestmark = [pytest.mark.unit]


def test_configured_scan_creates_records_and_exposes_paged_dashboard(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.opus").write_bytes(b"not-real-audio")
    service.save_audio_root(source)

    summary = service.scan_audio()
    assert summary.discovered == 1
    assert service.dashboard_counts().total == 1
    page = service.transcript_page(limit=10)
    assert page.total == 1
    assert page.rows[0]["basename"] == "one.opus"


def test_export_and_backup_are_available_without_presentation_layer(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    assert service.export_all() == 0
    assert service.create_backup().suffix == ".dntbackup"


def test_worker_cannot_start_without_an_explicit_audio_test_folder(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()

    with pytest.raises(ValueError, match="folder audio uji"):
        service.start_transcription()


def test_dashboard_counts_only_the_active_audio_folder(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    selected = tmp_path / "selected"
    previous = tmp_path / "previous"
    selected.mkdir()
    previous.mkdir()
    (selected / "one.opus").write_bytes(b"selected")
    (previous / "old.opus").write_bytes(b"previous")
    service.save_audio_root(selected)
    service.scan_audio()
    service.save_audio_root(previous)
    service.scan_audio()
    service.save_audio_root(selected)

    assert service.dashboard_counts().total == 1


def test_prepare_test_batch_rejects_more_than_twenty_sources(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    source = tmp_path / "too-many"
    source.mkdir()
    for index in range(21):
        (source / f"{index:02d}.opus").write_bytes(b"synthetic")

    with pytest.raises(ValueError, match="lebih dari 20"):
        service.prepare_test_batch(source)


def test_explicit_file_selection_excludes_every_other_incomplete_file(tmp_path: Path) -> None:
    """The preflight's safe batch may never leave an archive implicitly queued."""
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    source = tmp_path / "source"
    source.mkdir()
    service.save_audio_root(source)
    connection = open_connection(paths.database_file)
    try:
        root_id = int(
            connection.execute(
                "INSERT INTO source_roots(kind, original_path, normalized_path, created_at) VALUES ('audio', ?, ?, 't')",
                (str(source.resolve()), str(source.resolve()).casefold()),
            ).lastrowid
        )
        ids: list[int] = []
        for index in range(3):
            audio_id = int(
                connection.execute(
                    """INSERT INTO audio_files(stable_file_id, source_root_id, current_relative_path, basename,
                       normalized_basename, extension, size_bytes, first_discovered_at, last_seen_at,
                       current_state, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, '.opus', 1, 't', 't', 'discovered', 't', 't')""",
                    (f"candidate-{index}", root_id, f"{index}.opus", f"{index}.opus", f"{index}.opus"),
                ).lastrowid
            )
            connection.execute(
                "INSERT INTO audio_source_versions(audio_file_id, size_bytes, sha256, discovered_at) VALUES (?, 1, ?, 't')",
                (audio_id, f"hash-{index}"),
            )
            version = connection.execute(
                "SELECT id FROM audio_source_versions WHERE audio_file_id = ?", (audio_id,)
            ).fetchone()
            connection.execute(
                "UPDATE audio_files SET current_source_version_id = ? WHERE id = ?",
                (version["id"], audio_id),
            )
            ids.append(audio_id)
    finally:
        connection.close()

    page = service.transcription_candidates()
    assert page.total == 3
    assert {int(row["id"]) for row in page.rows} == set(ids)
    assert service.replace_transcription_selection([ids[1]]) == 1

    connection = open_connection(paths.database_file, read_only=True)
    try:
        rows = connection.execute(
            "SELECT id, transcription_enabled, current_state FROM audio_files ORDER BY id"
        ).fetchall()
    finally:
        connection.close()
    assert [(int(row["transcription_enabled"]), str(row["current_state"])) for row in rows] == [
        (0, "excluded"),
        (1, "discovered"),
        (0, "excluded"),
    ]


def test_manual_metadata_is_versioned_and_preserves_parser_source(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.opus").write_bytes(b"not-real-audio")
    service.save_audio_root(source)
    service.scan_audio()
    page = service.transcript_page(limit=10)
    audio_id = int(page.rows[0]["id"])

    service.save_manual_metadata(
        audio_id,
        sender="Synthetic Sender",
        chat="Synthetic Chat",
        whatsapp_message_at="2026-07-16T20:31:00+07:00",
    )
    service.save_manual_metadata(
        audio_id,
        sender="Synthetic Sender v2",
        chat="Synthetic Chat",
        whatsapp_message_at="2026-07-16T20:32:00+07:00",
    )

    detail = service.transcript_detail(audio_id)
    assert detail["sender"] == "Synthetic Sender v2"
