"""Application use cases exercise services without importing the Qt layer."""

from __future__ import annotations

import hashlib
import wave
from pathlib import Path

import pytest

from app.database.connection import open_connection
from app.paths import DataPaths
from app.services.application_service import ApplicationService

pytestmark = [pytest.mark.unit]


def _write_silent_wav(path: Path, *, frames: int = 800) -> None:
    """Create a tiny valid fixture without using any private audio."""
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8_000)
        stream.writeframes(b"\x00\x00" * frames)


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


def test_worker_cannot_start_without_explicit_audio_selection(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()

    with pytest.raises(ValueError, match="Tambahkan file audio"):
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


def _service_with_states(tmp_path: Path, states: dict[str, int]) -> ApplicationService:
    """Build one audio row per requested state so card arithmetic can be checked."""
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    source = tmp_path / "source"
    source.mkdir()
    (source / "seed.opus").write_bytes(b"seed")
    service.save_audio_root(source)
    service.scan_audio()

    connection = open_connection(paths.database_file)
    try:
        root_id = int(connection.execute("SELECT id FROM source_roots LIMIT 1").fetchone()[0])
        connection.execute("DELETE FROM audio_files")
        index = 0
        for state, count in states.items():
            for _ in range(count):
                index += 1
                connection.execute(
                    """INSERT INTO audio_files(stable_file_id, source_root_id,
                       current_relative_path, basename, normalized_basename, extension,
                       size_bytes, first_discovered_at, last_seen_at, current_state,
                       created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, '.opus', 1, 't', 't', ?, 't', 't')""",
                    (f"id-{index}", root_id, f"f{index}.opus", f"f{index}.opus", f"f{index}.opus", state),
                )
        connection.commit()
    finally:
        connection.close()
    return service


def test_dashboard_cards_account_for_every_row(tmp_path: Path) -> None:
    """P0-3 regression: excluded and no_speech rows used to vanish from the cards."""
    service = _service_with_states(
        tmp_path,
        {
            "completed_preferred": 3,
            "verified": 1,
            "discovered": 2,
            "queued": 1,
            "processing": 1,
            "stale_source_changed": 1,
            "failed": 2,
            "missing_source": 1,
            "excluded": 4,
            "no_speech": 2,
        },
    )
    counts = service.dashboard_counts()
    assert counts.total == 18
    assert counts.completed == 4  # completed_preferred + verified
    assert counts.pending == 5  # discovered + queued + processing + stale_source_changed
    assert counts.failed == 3  # failed + missing_source
    assert counts.excluded == 4
    assert counts.no_speech == 2
    assert counts.accounted() == counts.total


def test_review_card_equals_the_review_page_total(tmp_path: Path) -> None:
    """P0-3 regression: the card counted a different set than the page listed."""
    service = _service_with_states(
        tmp_path,
        {
            "completed_preferred": 2,
            "failed": 2,
            "missing_source": 1,
            "stale_source_changed": 3,
            "discovered": 4,
        },
    )
    counts = service.dashboard_counts()
    assert counts.review == service.review_page(limit=100).total
    # stale_source_changed belongs to the review page, so the old
    # failed+missing_source card could never have matched it.
    assert counts.review == 6


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


def test_direct_audio_files_use_separate_parents_and_remain_unchanged(tmp_path: Path) -> None:
    """Picker/drop batches are explicit, bounded, multi-location, and read-only."""
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = first_dir / "first.wav"
    second = second_dir / "second.wav"
    _write_silent_wav(first)
    _write_silent_wav(second, frames=1_600)
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (first, second)}

    summary = service.add_audio_files([first, second])

    assert summary.source_count == 2
    assert summary.selected_count == 2
    assert service.dashboard_counts().total == 2
    assert service.transcription_candidates().total == 2
    assert service.configured_audio_roots() == [first_dir.resolve(), second_dir.resolve()]
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (first, second)} == before


def test_direct_batch_never_replaces_the_configured_archive_folder(tmp_path: Path) -> None:
    """P0-4 regression: picking loose files used to silently discard the archive."""
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "arsip.opus").write_bytes(b"archived-voice-note")
    service.save_audio_root(archive)
    service.scan_audio()

    elsewhere = tmp_path / "downloads"
    elsewhere.mkdir()
    picked = elsewhere / "picked.wav"
    _write_silent_wav(picked)
    service.add_audio_files([picked])

    # The archive stays the scan root and the settings field keeps showing it.
    assert service.configured_audio_root() == archive.resolve()
    assert service.configured_direct_roots() == [elsewhere.resolve()]
    # Scope is the union, so nothing the user already had disappears.
    assert service.configured_audio_roots() == [archive.resolve(), elsewhere.resolve()]
    assert service.dashboard_counts().total == 2

    # "Scan File Baru" still walks the archive, not the downloads folder.
    (archive / "arsip-2.opus").write_bytes(b"second-archived-voice-note")
    assert service.scan_audio().discovered == 1
    assert service.dashboard_counts().total == 3

    service.clear_direct_roots()
    assert service.configured_direct_roots() == []
    assert service.configured_audio_root() == archive.resolve()
    assert service.dashboard_counts().total == 2


def test_scan_summary_keeps_discovered_count_when_an_unchanged_file_follows(
    tmp_path: Path,
) -> None:
    """P0-7 regression: a later unchanged file used to reset `discovered` to 0.

    `_scan_one` rebuilt the whole summary per branch, so the counter reported to
    the user depended on filename order.
    """
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    source = tmp_path / "source"
    source.mkdir()
    # "b-old" sorts after "a-new", so the new file is scanned first and the
    # unchanged one second: the exact order that erased the count.
    _write_silent_wav(source / "b-old.wav")
    service.save_audio_root(source)
    assert service.scan_audio().discovered == 1

    _write_silent_wav(source / "a-new.wav", frames=1_600)
    summary = service.scan_audio()
    assert summary.discovered == 1
    assert summary.unchanged == 1


def test_scan_reports_progress_so_a_large_archive_never_looks_frozen(tmp_path: Path) -> None:
    """P1-4 regression: a first scan hashes every byte and said nothing meanwhile."""
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    source = tmp_path / "source"
    source.mkdir()
    for index in range(30):
        _write_silent_wav(source / f"voice-{index:03d}.wav", frames=800 + index)
    service.save_audio_root(source)

    seen: list[tuple[int, int]] = []
    summary = service.scan_audio(progress=lambda done, total: seen.append((done, total)))

    assert summary.discovered == 30
    assert seen[0] == (0, 30)
    assert seen[-1] == (30, 30)
    # Progress must be reported during the walk, not only at the end.
    assert len(seen) >= 2


def test_direct_batch_folders_accumulate_without_duplicates(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    folder = tmp_path / "drop"
    folder.mkdir()
    first = folder / "a.wav"
    second = folder / "b.wav"
    _write_silent_wav(first)
    _write_silent_wav(second)

    service.add_audio_files([first])
    service.add_audio_files([second])

    assert service.configured_direct_roots() == [folder.resolve()]


def test_direct_batch_accepts_far_more_than_the_old_twenty_file_cap(tmp_path: Path) -> None:
    """P1-1 regression: the product exists to process an archive of thousands.

    The 20-file cap was a build-time guard for the coding agent that shipped by
    mistake, and it made the main workflow impossible.
    """
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    folder = tmp_path / "source"
    folder.mkdir()
    # Distinct lengths keep the SHA-256 identities distinct; identical bytes
    # would legitimately collapse into one relinked record.
    files = [folder / f"{index}.wav" for index in range(120)]
    for index, path in enumerate(files):
        _write_silent_wav(path, frames=800 + index)

    summary = service.add_audio_files(files)

    assert summary.source_count == 120
    assert summary.selected_count == 120
    assert service.transcription_candidates(limit=500).total == 120


def test_direct_batch_still_refuses_an_absurd_number_of_files(tmp_path: Path) -> None:
    """A rail against selecting a whole drive, not a product limit."""
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    folder = tmp_path / "source"
    folder.mkdir()
    real = folder / "one.wav"
    _write_silent_wav(real)

    with pytest.raises(ValueError, match="maksimal"):
        service.add_audio_files([real], maximum_files=0)


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
