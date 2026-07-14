"""Synthetic parser coverage for every Phase 4 blueprint format."""

from __future__ import annotations

import pytest

from app.parsing.whatsapp_parser import PARSER_VERSION, duplicate_export_hashes, parse_export

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize(
    ("text", "timestamp", "sender", "filename"),
    [
        (
            "14/07/2026, 20.31 - Daniel: PTT-20260714-WA0043.opus",
            "2026-07-14T20:31:00",
            "Daniel",
            "PTT-20260714-WA0043.opus",
        ),
        (
            "[14/07/2026, 20:31:00] Daniel: PTT-20260714-WA0043.opus",
            "2026-07-14T20:31:00",
            "Daniel",
            "PTT-20260714-WA0043.opus",
        ),
        (
            "7/14/26, 8:31 PM - Daniel: PTT-20260714-WA0043.opus",
            "2026-07-14T20:31:00",
            "Daniel",
            "PTT-20260714-WA0043.opus",
        ),
    ],
)
def test_parse_common_header_formats(text: str, timestamp: str, sender: str, filename: str) -> None:
    reference = parse_export(text, chat_name="Synthetic Chat").references[0]
    assert reference.whatsapp_message_at == timestamp
    assert reference.sender_original == sender
    assert reference.referenced_filename == filename
    assert reference.chat_original == "Synthetic Chat"
    assert PARSER_VERSION == "1.0"


def test_bom_direction_marks_multiline_and_colon_in_sender() -> None:
    text = "\ufeff\u200e14/07/26, 20:31 - Dr. Budi: S.Kom: PTT-A.opus\nlanjutan pesan"
    reference = parse_export(text).references[0]
    assert reference.sender_original == "Dr. Budi: S.Kom"
    assert reference.referenced_filename == "PTT-A.opus"


def test_system_message_is_not_a_voice_reference() -> None:
    text = "Messages and calls are end-to-end encrypted.\n14/07/26, 20:31 - Daniel joined using this group's invite link"
    assert parse_export(text).references == []


def test_omitted_media_preserves_unknown_filename_without_fabrication() -> None:
    reference = parse_export("14/07/26, 20:31 - Daniel: <Media omitted>").references[0]
    assert reference.referenced_filename is None
    assert reference.warning == "filename_not_present"
    assert reference.parser_confidence < 0.9


def test_duplicate_export_detection_uses_normalized_content_hash() -> None:
    duplicate = duplicate_export_hashes(
        {"first.txt": "\ufeffsame", "second.txt": "same", "third.txt": "different"}
    )
    assert duplicate == {"second.txt": "first.txt"}


def test_unmatched_content_is_counted_without_returning_or_logging_it() -> None:
    result = parse_export("unrecognised system content\n14/07/26, 20:31 - Daniel: PTT-A.opus")
    assert result.unmatched_header_count == 1
    assert len(result.references) == 1
