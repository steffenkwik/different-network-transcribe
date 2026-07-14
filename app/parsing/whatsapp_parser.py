"""Versioned, privacy-conscious WhatsApp text-export parser."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

PARSER_VERSION = "1.0"
_DIRECTION_MARKS = "\u200e\u200f\u202a\u202b\u202c\u202d\u202e"
_HEADER_PATTERNS = (
    (
        "bracketed",
        re.compile(
            r"^\[(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{2,4}),\s*"
            r"(?P<time>\d{1,2}[.:]\d{2}(?::\d{2})?(?:\s*[AaPp][Mm])?)\]\s*(?P<payload>.+)$"
        ),
    ),
    (
        "dash",
        re.compile(
            r"^(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{2,4}),\s*"
            r"(?P<time>\d{1,2}[.:]\d{2}(?::\d{2})?(?:\s*[AaPp][Mm])?)\s*-\s*(?P<payload>.+)$"
        ),
    ),
)
_FILENAME_RE = re.compile(
    r"(?P<filename>[\w.()\- ]+?\.(?:opus|ogg|mp3|wav|m4a|aac|flac|webm|mp4))\b",
    re.IGNORECASE,
)
_OMITTED_RE = re.compile(r"<(?:media omitted|media tidak disertakan)>", re.IGNORECASE)


@dataclass(frozen=True)
class ChatVoiceReference:
    line_number: int
    sender_original: str | None
    chat_original: str | None
    whatsapp_message_at: str | None
    referenced_filename: str | None
    normalized_filename: str | None
    parser_pattern: str
    parser_confidence: float
    warning: str | None
    header_hash: str


@dataclass(frozen=True)
class ParseResult:
    references: list[ChatVoiceReference]
    warning_count: int
    unmatched_header_count: int


def _clean(text: str) -> str:
    return text.removeprefix("\ufeff").translate(str.maketrans("", "", _DIRECTION_MARKS))


def _parse_datetime(date_text: str, time_text: str) -> str | None:
    """Parse common Indonesian/English WhatsApp dates; ambiguous numeric dates default D/M/Y."""
    parts = re.split(r"[/-]", date_text)
    if len(parts) != 3:
        return None
    first, second, year = (int(part) for part in parts)
    if year < 100:
        year += 2000
    uses_ampm = bool(re.search(r"[AaPp][Mm]", time_text))
    # English 12-hour examples are conventionally M/D/Y; unambiguous >12 is
    # always D/M/Y. For values 1..12 without AM/PM, use Indonesian D/M/Y.
    month, day = (first, second) if uses_ampm and first <= 12 else (second, first)
    normalized_time = time_text.replace(".", ":").upper().strip()
    for time_format in ("%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(
                f"{year:04d}-{month:02d}-{day:02d} {normalized_time}", f"%Y-%m-%d {time_format}"
            )
            return parsed.isoformat(timespec="seconds")
        except ValueError:
            continue
    return None


def _header(line: str) -> tuple[str, re.Match[str]] | None:
    for pattern_id, pattern in _HEADER_PATTERNS:
        match = pattern.match(line)
        if match is not None:
            return pattern_id, match
    return None


def _split_sender_payload(payload: str) -> tuple[str | None, str]:
    """Use the final colon, so a sender name may itself contain colons."""
    if ":" not in payload:
        return None, payload
    sender, body = payload.rsplit(":", 1)
    sender = sender.strip()
    return (sender or None), body.strip()


def _header_hash(line: str) -> str:
    return hashlib.sha256(line.casefold().encode("utf-8")).hexdigest()


def parse_export(text: str, *, chat_name: str | None = None) -> ParseResult:
    """Extract voice-attachment metadata while discarding unrelated chat bodies."""
    lines = _clean(text).splitlines()
    messages: list[tuple[int, str, str, str, str]] = []
    current: list[str] | None = None
    unmatched_headers = 0

    for number, raw_line in enumerate(lines, start=1):
        parsed_header = _header(raw_line)
        if parsed_header is not None:
            if current is not None:
                messages.append((int(current[0]), current[1], current[2], current[3], current[4]))
            pattern_id, match = parsed_header
            current = [
                str(number),
                pattern_id,
                match.group("date"),
                match.group("time"),
                match.group("payload"),
            ]
        elif current is not None:
            current[4] = f"{current[4]}\n{raw_line}"
        elif raw_line.strip():
            unmatched_headers += 1
    if current is not None:
        messages.append((int(current[0]), current[1], current[2], current[3], current[4]))

    references: list[ChatVoiceReference] = []
    for line_number, pattern_id, date_text, time_text, payload in messages:
        sender, body = _split_sender_payload(payload)
        filename_match = _FILENAME_RE.search(body)
        omitted = _OMITTED_RE.search(body) is not None
        if filename_match is None and not omitted:
            continue
        filename = None if filename_match is None else filename_match.group("filename").strip()
        warning = "filename_not_present" if omitted and filename is None else None
        header = f"{date_text},{time_text}|{payload.splitlines()[0]}"
        references.append(
            ChatVoiceReference(
                line_number=line_number,
                sender_original=sender,
                chat_original=chat_name,
                whatsapp_message_at=_parse_datetime(date_text, time_text),
                referenced_filename=filename,
                normalized_filename=None if filename is None else filename.casefold(),
                parser_pattern=pattern_id,
                parser_confidence=1.0 if filename is not None else 0.6,
                warning=warning,
                header_hash=_header_hash(header),
            )
        )
    return ParseResult(
        references=references,
        warning_count=sum(reference.warning is not None for reference in references),
        unmatched_header_count=unmatched_headers,
    )


def duplicate_export_hashes(exports: dict[str, str]) -> dict[str, str]:
    """Return a duplicate path -> canonical path map without retaining chat content."""
    canonical_for_hash: dict[str, str] = {}
    duplicates: dict[str, str] = {}
    for path, content in exports.items():
        digest = hashlib.sha256(_clean(content).encode("utf-8")).hexdigest()
        if digest in canonical_for_hash:
            duplicates[path] = canonical_for_hash[digest]
        else:
            canonical_for_hash[digest] = path
    return duplicates
