"""The worker-status snapshot shared by the worker process and the UI.

Progress must describe *the run the user just started*.  The previous format
published an all-time completed count next to the remaining queue, so a fresh
20-file run on an archive with 500 finished files rendered as "96% selesai"
before the first file was even transcribed.  Session counters live here, and the
UI never derives progress from anything else.

This module is deliberately Qt-free: the worker writes it, the UI reads it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Bumped from 1: v1 files carried no honest session counters.
STATUS_SCHEMA = 2

#: States in which a worker process is still alive and worth polling.
LIVE_WORKER_STATES = frozenset({"preparing", "running", "pausing", "paused", "idle"})

_STATE_LABELS = {
    "preparing": "Menyiapkan antrean",
    "running": "Sedang mentranskripsi",
    "pausing": "Menjeda",
    "paused": "Dijeda",
    "idle": "Menunggu pekerjaan baru",
    "stopped": "Dihentikan dengan aman",
    "finished": "Antrean selesai",
    "failed": "Worker gagal",
}


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


@dataclass
class SessionProgress:
    """Counters for one worker session. Never includes work from earlier runs."""

    total: int = 0
    done: int = 0
    failed: int = 0
    current_file: str | None = None
    started_at: str = field(default_factory=_now)
    _elapsed_seconds: float = 0.0

    def start_file(self, basename: str) -> None:
        self.current_file = basename

    def record_finished(self, seconds: float, *, failed: bool = False) -> None:
        """Record one completed attempt and the wall time it actually took."""
        if failed:
            self.failed += 1
        else:
            self.done += 1
        self._elapsed_seconds += max(0.0, seconds)
        self.current_file = None

    @property
    def finished(self) -> int:
        return self.done + self.failed

    @property
    def remaining(self) -> int:
        return max(0, self.total - self.finished)

    def avg_seconds_per_file(self) -> float | None:
        if self.finished == 0:
            return None
        return self._elapsed_seconds / self.finished

    def eta_seconds(self) -> float | None:
        average = self.avg_seconds_per_file()
        if average is None or self.remaining == 0:
            return None
        return average * self.remaining

    def as_payload(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "total": self.total,
            "done": self.done,
            "failed": self.failed,
            "current_file": self.current_file,
            "avg_seconds_per_file": self.avg_seconds_per_file(),
            "eta_seconds": self.eta_seconds(),
        }


def read_status(path: Path) -> dict[str, Any] | None:
    """Read a status snapshot, tolerating a partially written or absent file."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _session_of(status: dict[str, Any]) -> dict[str, Any] | None:
    session = status.get("session")
    return session if isinstance(session, dict) else None


def _as_int(value: object) -> int:
    """Coerce a JSON field written by another process; never trust its type."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def is_live(status: dict[str, Any]) -> bool:
    return str(status.get("state", "")) in LIVE_WORKER_STATES


def progress_percent(status: dict[str, Any]) -> int:
    """Percent of *this session* finished, or 0 when no session count exists.

    A schema-1 file has no session counters. Returning 0 keeps the bar honest
    rather than reviving the old all-time ratio.
    """
    session = _session_of(status)
    if session is None:
        return 0
    total = _as_int(session.get("total"))
    if total <= 0:
        return 0
    finished = _as_int(session.get("done")) + _as_int(session.get("failed"))
    return max(0, min(100, round(100 * finished / total)))


def format_duration(seconds: float | None) -> str | None:
    """Render a coarse Indonesian duration; precision here would be false comfort."""
    if seconds is None or seconds < 0:
        return None
    minutes = int(seconds // 60)
    if minutes < 1:
        return "kurang dari 1 menit"
    if minutes < 60:
        return f"{minutes} menit"
    hours, remainder = divmod(minutes, 60)
    if remainder == 0:
        return f"{hours} jam"
    return f"{hours} jam {remainder} menit"


def status_text(status: dict[str, Any]) -> str:
    """One human sentence for the worker card, in Indonesian."""
    safe_message = status.get("last_safe_message")
    if isinstance(safe_message, str) and safe_message:
        return safe_message
    state = str(status.get("state", ""))
    label = _STATE_LABELS.get(state, f"Worker: {state or 'tidak diketahui'}")
    if state == "preparing":
        # Preparing an archive of thousands takes a while; saying so with a
        # position is the difference between "working" and "frozen".
        prepare = status.get("prepare")
        if isinstance(prepare, dict) and _as_int(prepare.get("total")) > 0:
            return (
                f"{label}… {_as_int(prepare.get('done'))}/{_as_int(prepare.get('total'))} file diperiksa"
            )
        return f"{label}…"
    session = _session_of(status)
    if session is None:
        return label
    total = _as_int(session.get("total"))
    if total <= 0:
        return label
    finished = _as_int(session.get("done")) + _as_int(session.get("failed"))
    parts = [f"{label} · {finished}/{total} file"]
    current = session.get("current_file")
    if isinstance(current, str) and current and state == "running":
        parts.append(current)
    eta = session.get("eta_seconds")
    if state == "running" and isinstance(eta, int | float):
        readable = format_duration(float(eta))
        if readable is not None:
            parts.append(f"sisa ±{readable}")
    failed = _as_int(session.get("failed"))
    if failed:
        parts.append(f"{failed} gagal")
    return " · ".join(parts)
