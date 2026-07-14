"""SQLite connection lifecycle and transaction helpers.

Each caller opens its own connection.  This keeps SQLite ownership explicit across
the UI process, worker process, and background tasks.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def open_connection(database_file: Path, *, read_only: bool = False) -> sqlite3.Connection:
    """Open and configure one SQLite connection for one thread/process."""
    if read_only:
        uri = f"file:{database_file.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5.0, isolation_level=None)
    else:
        database_file.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database_file, timeout=5.0, isolation_level=None)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    if not read_only:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
    return connection


@contextmanager
def transaction(connection: sqlite3.Connection, *, immediate: bool = False) -> Iterator[None]:
    """Run a short transaction and roll it back on every exception."""
    connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    else:
        connection.execute("COMMIT")


def quick_check(connection: sqlite3.Connection) -> str:
    """Fast startup integrity validation required by the technical addendum."""
    return str(connection.execute("PRAGMA quick_check").fetchone()[0])


def integrity_check(connection: sqlite3.Connection) -> str:
    """Full integrity validation, used only for explicit validation/restore."""
    return str(connection.execute("PRAGMA integrity_check").fetchone()[0])
