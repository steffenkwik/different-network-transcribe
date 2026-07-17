"""Read-only audio discovery and SHA-256 source-version tracking."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from app.database.connection import transaction
from app.database.repositories import AudioRepository, now

SUPPORTED_AUDIO_EXTENSIONS = frozenset(
    {".opus", ".ogg", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".webm", ".mp4"}
)
DurationProbe = Callable[[Path], float | None]


@dataclass(frozen=True)
class ScanSummary:
    discovered: int = 0
    unchanged: int = 0
    relinked: int = 0
    source_changed: int = 0
    unreadable: int = 0
    zero_byte: int = 0
    missing: int = 0
    duplicate_basenames: int = 0


def iso_local(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).astimezone().isoformat(timespec="seconds")


def normalized_path(path: Path) -> str:
    return str(path.resolve()).casefold().replace("\\", "/")


def normalized_relative_path(path: Path) -> str:
    return path.as_posix().casefold()


def sha256_file(path: Path) -> str:
    """Hash a source file without changing it."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pyav_duration_seconds(path: Path) -> float | None:
    """Read duration directly through PyAV; decoding errors do not mutate the input."""
    import av

    with av.open(path) as container:
        duration = container.duration
    return None if duration is None else float(duration / av.time_base)


class DiscoveryService:
    """Scans sources while preserving source files as strictly read-only inputs."""

    def __init__(
        self, connection: sqlite3.Connection, duration_probe: DurationProbe = pyav_duration_seconds
    ) -> None:
        self.connection = connection
        self.repository = AudioRepository(connection)
        self.duration_probe = duration_probe

    def scan_audio_root(self, root: Path) -> ScanSummary:
        root = root.resolve()
        if not root.is_dir():
            raise ValueError("Folder audio tidak ditemukan atau bukan folder.")
        with transaction(self.connection, immediate=True):
            source_root_id = self.repository.source_root(
                kind="audio", original_path=str(root), normalized_path=normalized_path(root)
            )

        summary = ScanSummary()
        seen: set[str] = set()
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.casefold() not in SUPPORTED_AUDIO_EXTENSIONS:
                continue
            relative_path = normalized_relative_path(path.relative_to(root))
            seen.add(relative_path)
            summary = self._scan_one(path, source_root_id, relative_path, summary)

        with transaction(self.connection, immediate=True):
            missing = self.repository.mark_missing_paths(source_root_id, seen)
            self.repository.finish_root_scan(source_root_id)
            self.repository.refresh_duplicate_groups()
            duplicate_basenames = int(
                self.connection.execute(
                    "SELECT COUNT(DISTINCT duplicate_group) FROM audio_files WHERE duplicate_group IS NOT NULL"
                ).fetchone()[0]
            )
        return ScanSummary(
            discovered=summary.discovered,
            unchanged=summary.unchanged,
            relinked=summary.relinked,
            source_changed=summary.source_changed,
            unreadable=summary.unreadable,
            zero_byte=summary.zero_byte,
            missing=missing,
            duplicate_basenames=duplicate_basenames,
        )

    def scan_audio_files(self, files: list[Path]) -> ScanSummary:
        """Register an explicit file list without recursively scanning its folders.

        This is the safe path behind the desktop file picker and drag-and-drop
        zone.  Sources are read only and each selected file is rooted at its own
        parent directory, so users may select files from several locations.
        Unlike ``scan_audio_root`` this deliberately never marks sibling files
        missing: the user did not ask us to inspect a whole folder.
        """
        selected = sorted({path.resolve() for path in files}, key=normalized_path)
        if not selected:
            return ScanSummary()

        roots: dict[Path, int] = {}
        with transaction(self.connection, immediate=True):
            for path in selected:
                if not path.is_file() or path.suffix.casefold() not in SUPPORTED_AUDIO_EXTENSIONS:
                    raise ValueError(f"File audio tidak didukung: {path.name}")
                root = path.parent
                if root not in roots:
                    roots[root] = self.repository.source_root(
                        kind="audio", original_path=str(root), normalized_path=normalized_path(root)
                    )

        summary = ScanSummary()
        for path in selected:
            summary = _combine_scan_summaries(
                summary,
                self._scan_one(path, roots[path.parent], normalized_relative_path(Path(path.name)), ScanSummary()),
            )

        with transaction(self.connection, immediate=True):
            for source_root_id in roots.values():
                self.repository.finish_root_scan(source_root_id)
            self.repository.refresh_duplicate_groups()
            duplicate_basenames = int(
                self.connection.execute(
                    "SELECT COUNT(DISTINCT duplicate_group) FROM audio_files WHERE duplicate_group IS NOT NULL"
                ).fetchone()[0]
            )
        return ScanSummary(
            discovered=summary.discovered,
            unchanged=summary.unchanged,
            relinked=summary.relinked,
            source_changed=summary.source_changed,
            unreadable=summary.unreadable,
            zero_byte=summary.zero_byte,
            duplicate_basenames=duplicate_basenames,
        )

    def _scan_one(
        self, path: Path, source_root_id: int, relative_path: str, summary: ScanSummary
    ) -> ScanSummary:
        timestamp = now()
        try:
            stat = path.stat()
            size_bytes = stat.st_size
            zero_byte = size_bytes == 0
            digest = None if zero_byte else sha256_file(path)
            duration = None if zero_byte else self.duration_probe(path)
            readable = True
        except Exception:  # A decoder error is isolated to this one source record.
            stat = None
            size_bytes = 0
            zero_byte = False
            digest = None
            duration = None
            readable = False

        values = {
            "source_root_id": source_root_id,
            "current_relative_path": relative_path,
            "basename": path.name,
            "normalized_basename": path.name.casefold(),
            "extension": path.suffix.casefold(),
            "size_bytes": size_bytes,
            "windows_created_at": None if stat is None else iso_local(stat.st_ctime),
            "windows_modified_at": None if stat is None else iso_local(stat.st_mtime),
            "last_seen_at": timestamp,
            "duration_seconds": duration,
            "sha256": digest,
            "readable": int(readable),
            "zero_byte": int(zero_byte),
            "updated_at": timestamp,
        }

        with transaction(self.connection, immediate=True):
            at_path = self.repository.audio_at_path(source_root_id, relative_path)
            if at_path is not None and str(at_path["version_sha256"] or "") == str(digest or ""):
                self.repository.update_audio_observation(int(at_path["id"]), values)
                self.repository.record_path(int(at_path["id"]), source_root_id, relative_path)
                return ScanSummary(
                    unchanged=summary.unchanged + 1,
                    unreadable=summary.unreadable + int(not readable),
                    zero_byte=summary.zero_byte + int(zero_byte),
                )

            if digest is not None:
                known = self.repository.audio_for_sha256(digest)
                if known is not None:
                    self.repository.update_audio_observation(int(known["id"]), values)
                    self.repository.record_path(int(known["id"]), source_root_id, relative_path)
                    if at_path is not None and int(known["id"]) == int(at_path["id"]):
                        self.repository.mark_source_version_current(
                            int(known["id"]), int(known["matched_source_version_id"])
                        )
                        self.repository.set_state(int(known["id"]), "stale_source_changed")
                        return ScanSummary(source_changed=summary.source_changed + 1)
                    return ScanSummary(relinked=summary.relinked + 1)

            if at_path is not None:
                self.repository.update_audio_observation(int(at_path["id"]), values)
                if digest is not None:
                    version_id = self.repository.add_source_version(
                        int(at_path["id"]),
                        size_bytes=size_bytes,
                        modified_at=cast(str | None, values["windows_modified_at"]),
                        sha256=digest,
                    )
                    self.repository.mark_source_version_current(int(at_path["id"]), version_id)
                    self.repository.set_state(int(at_path["id"]), "stale_source_changed")
                self.repository.record_path(int(at_path["id"]), source_root_id, relative_path)
                return ScanSummary(source_changed=summary.source_changed + 1)

            audio_id = self.repository.create_audio(
                {
                    **values,
                    "stable_file_id": uuid.uuid4().hex,
                    "first_discovered_at": timestamp,
                    "current_state": "discovered"
                    if readable and not zero_byte
                    else "missing_source",
                    "created_at": timestamp,
                }
            )
            if digest is not None:
                version_id = self.repository.add_source_version(
                    audio_id,
                    size_bytes=size_bytes,
                    modified_at=cast(str | None, values["windows_modified_at"]),
                    sha256=digest,
                )
                self.repository.mark_source_version_current(audio_id, version_id)
            self.repository.record_path(audio_id, source_root_id, relative_path)
            return ScanSummary(
                discovered=summary.discovered + 1,
                unreadable=summary.unreadable + int(not readable),
                zero_byte=summary.zero_byte + int(zero_byte),
            )


def _combine_scan_summaries(first: ScanSummary, second: ScanSummary) -> ScanSummary:
    """Add per-file scan results without losing the aggregate safety counters."""
    return ScanSummary(
        discovered=first.discovered + second.discovered,
        unchanged=first.unchanged + second.unchanged,
        relinked=first.relinked + second.relinked,
        source_changed=first.source_changed + second.source_changed,
        unreadable=first.unreadable + second.unreadable,
        zero_byte=first.zero_byte + second.zero_byte,
        missing=first.missing + second.missing,
        duplicate_basenames=max(first.duplicate_basenames, second.duplicate_basenames),
    )
