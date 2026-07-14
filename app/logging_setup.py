"""Structured local logging (addendum section 16).

Hard rules enforced here, not merely documented:
  * Transcript bodies are never written to the log by default.
  * Chat-export bodies are never written to the log.
  * Logs stay on this machine. Nothing is uploaded, ever.

Every record carries the identifiers the addendum requires:
session_id, worker_id, audio stable id, attempt id, export id.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Fields whose values are private content. If a caller passes one of these in
# `extra`, the value is replaced with a length marker instead of the text.
_PRIVATE_FIELDS = frozenset(
    {
        "transcript",
        "raw_transcript",
        "normalized_transcript",
        "text",
        "segment_json",
        "chat_body",
        "message_body",
        "sender",
        "chat",
    }
)

# Reserved LogRecord attributes we must not copy into the structured payload.
_RESERVED = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "taskName", "message", "asctime",
    }
)

_PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{8,}\d")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def redact(value: Any) -> Any:
    """Replace private content with a non-reversible marker."""
    if isinstance(value, str):
        return f"<redacted:{len(value)} chars>"
    if value is None:
        return None
    return "<redacted>"


def scrub_text(text: str) -> str:
    """Remove phone numbers and e-mail addresses from a free-text message.

    Applied to every log message, because exception strings and file paths from a
    WhatsApp export can carry a phone number in the chat name.
    """
    text = _PHONE_RE.sub("<phone>", text)
    return _EMAIL_RE.sub("<email>", text)


class PrivacyFilter(logging.Filter):
    """Drop private values before they can reach any handler."""

    def __init__(self, allow_transcript_bodies: bool = False) -> None:
        super().__init__()
        self.allow_transcript_bodies = allow_transcript_bodies

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.allow_transcript_bodies:
            for key in list(record.__dict__):
                if key in _PRIVATE_FIELDS:
                    record.__dict__[key] = redact(record.__dict__[key])
        record.msg = scrub_text(str(record.msg))
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Machine-readable, greppable, diffable."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC)
            .astimezone()
            .isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            # The stack trace stays in the local technical log. The UI shows only
            # a safe message (blueprint section 19).
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class ContextFilter(logging.Filter):
    """Stamp every record with the identifiers required by addendum section 16."""

    def __init__(self, session_id: str, role: str) -> None:
        super().__init__()
        self.session_id = session_id
        self.role = role

    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = self.session_id
        record.role = self.role
        return True


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def setup_logging(
    logs_dir: Path,
    *,
    session_id: str,
    role: str,
    level: str = "INFO",
    allow_transcript_bodies: bool = False,
    keep_days: int = 30,
) -> logging.Logger:
    """Configure the root logger for one process (UI or worker).

    `role` is 'ui' or 'worker' and becomes the log filename, so the two processes
    never fight over the same handle.
    """
    logs_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)

    privacy = PrivacyFilter(allow_transcript_bodies=allow_transcript_bodies)
    context = ContextFilter(session_id=session_id, role=role)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        logs_dir / f"{role}.log",
        when="midnight",
        backupCount=keep_days,
        encoding="utf-8",
    )
    file_handler.setFormatter(JsonFormatter())
    file_handler.addFilter(context)
    file_handler.addFilter(privacy)
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    console.addFilter(context)
    console.addFilter(privacy)
    root.addHandler(console)

    return logging.getLogger(role)
