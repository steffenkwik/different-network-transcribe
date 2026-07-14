"""Logs must never contain transcript bodies, phone numbers, or e-mail addresses
(blueprint section 19, addendum section 16).

These tests read the log file back off disk, because "we pass the right arguments"
is not the same promise as "the bytes on disk are safe".
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from app.logging_setup import new_session_id, scrub_text, setup_logging

pytestmark = pytest.mark.unit

SECRET = "Besok kita lanjutkan pembahasan halaman utama."


def _read_log(logs_dir: Path, role: str) -> str:
    logging.shutdown()
    return (logs_dir / f"{role}.log").read_text(encoding="utf-8")


def test_transcript_body_never_reaches_the_log(tmp_path: Path) -> None:
    log = setup_logging(tmp_path, session_id=new_session_id(), role="worker")
    log.info("attempt completed", extra={"raw_transcript": SECRET, "audio_file_id": 7})

    contents = _read_log(tmp_path, "worker")
    assert SECRET not in contents
    assert "<redacted:" in contents
    assert '"audio_file_id": 7' in contents, "non-private identifiers must still be logged"


def test_sender_and_chat_are_redacted(tmp_path: Path) -> None:
    log = setup_logging(tmp_path, session_id=new_session_id(), role="ui")
    log.info("matched", extra={"sender": "Daniel", "chat": "Grup Different Network"})

    contents = _read_log(tmp_path, "ui")
    assert "Daniel" not in contents
    assert "Grup Different Network" not in contents


def test_phone_and_email_scrubbed_from_messages(tmp_path: Path) -> None:
    log = setup_logging(tmp_path, session_id=new_session_id(), role="ui")
    log.warning("gagal parse dari +62 812-3456-7890 dan orang@contoh.com")

    contents = _read_log(tmp_path, "ui")
    assert "812" not in contents
    assert "orang@contoh.com" not in contents
    assert "<phone>" in contents
    assert "<email>" in contents


def test_scrub_text_is_pure() -> None:
    assert scrub_text("hubungi +62 812 3456 7890") == "hubungi <phone>"
    assert scrub_text("kirim ke a.b+x@mail.co.id") == "kirim ke <email>"
    assert scrub_text("tidak ada apa-apa") == "tidak ada apa-apa"


def test_every_record_carries_session_id(tmp_path: Path) -> None:
    """Addendum section 16 requires session id on every record."""
    session = new_session_id()
    log = setup_logging(tmp_path, session_id=session, role="worker")
    log.info("lifecycle event")

    line = _read_log(tmp_path, "worker").strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["session_id"] == session
    assert payload["role"] == "worker"
    assert payload["level"] == "INFO"


def test_log_is_valid_jsonl(tmp_path: Path) -> None:
    log = setup_logging(tmp_path, session_id=new_session_id(), role="ui")
    log.info("one")
    log.warning("two")
    log.error("three")

    for line in _read_log(tmp_path, "ui").strip().splitlines():
        json.loads(line)


def test_opt_in_allows_transcript_logging(tmp_path: Path) -> None:
    """The redaction is a default, not a lie: DEBUG diagnostics can opt in."""
    log = setup_logging(
        tmp_path, session_id=new_session_id(), role="worker", allow_transcript_bodies=True
    )
    log.info("attempt", extra={"raw_transcript": SECRET})
    assert SECRET in _read_log(tmp_path, "worker")
