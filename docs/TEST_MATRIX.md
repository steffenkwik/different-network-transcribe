# Test Matrix

Implements `PROJECT_BLUEPRINT.md` §23 and `TECHNICAL_ADDENDUM.md` §26 deliverable 8:
*"test matrix mapped to every mandatory acceptance test"*.

Every mandatory acceptance scenario in the addendum has a named automated test. No scenario is left to manual inspection.

---

## 1. Mandatory acceptance tests (addendum §23–§25) — these are the ones that can fail the release

### Addendum §23 — NO-REPEAT (the highest-stakes test in the project)

| Step | Test | Asserts |
|---|---|---|
| 1–3 | `test_norepeat_initial_run` | 20 synthetic files scanned + transcribed; `attempt_count == 20` |
| 4–6 | `test_norepeat_restart_and_rescan` | App restart → rescan → start again |
| 7 | `test_norepeat_zero_new_attempts` | **0 new rows** in `transcription_attempts`; completed count unchanged |
| 7 | `test_norepeat_zero_inference` | `FakeEngine.transcribe_call_count == 0` on the second run — proves no model inference, not merely no DB writes |
| 7 | `test_norepeat_skip_events_recorded` | 20 `skipped_complete` rows in `processing_events` |
| 8–10 | `test_deleted_output_regenerates_without_transcription` | Delete generated MD+TXT → export again → files restored from SQLite, **0 new attempts** |
| 11–13 | `test_move_and_relink_no_new_attempt` | Move sources to a new folder → rescan → relink by SHA-256 → **0 new attempts**, path history recorded |

### Addendum §24 — SAFE STOP

| Step | Test | Asserts |
|---|---|---|
| 1–3 | `test_safe_stop_during_file_two` | 5 files queued; `safe_stop` issued while file 2 is in flight |
| 4a | `test_safe_stop_file_one_complete` | File 1 remains `completed` |
| 4b | `test_safe_stop_file_two_complete_or_requeued` | File 2 is **either** `completed` **or** back at `queued` — never half-written, never lost |
| 4c | `test_safe_stop_files_three_to_five_pending` | Files 3–5 still `queued` |
| 4d | `test_safe_stop_integrity` | `PRAGMA integrity_check` = ok |
| 4e | `test_safe_stop_lease_released` | `worker_sessions.state = 'stopped'`, lease gone |
| 4f | `test_safe_stop_restart_no_duplicate` | Restart → file 1 is **not** transcribed again |

### Addendum §25 — MODEL CHANGE

| Step | Test | Asserts |
|---|---|---|
| 1–4 | `test_model_change_does_not_reprocess_completed` | Complete with Small → default = Medium → start → **0 new attempts** for the Small-completed files |
| 5–6 | `test_new_file_uses_new_default_model` | A newly added file is transcribed with Medium |
| 7–8 | `test_explicit_reprocess_preserves_both_attempts` | Explicit Medium reprocess of one Small record → **both** attempts stored; `preferred_transcript_id` correct per §7.4 priority |

### Addendum §22 — PERFORMANCE THRESHOLDS (13,000 synthetic records)

| Target | Test | Threshold |
|---|---|---|
| Startup → usable dashboard | `test_perf_startup` | < 5 s (excl. model setup) |
| First table page | `test_perf_first_page` | < 1 s |
| Normal paginated query | `test_perf_paged_query` | < 500 ms |
| Filter / search on indexed field | `test_perf_filter_query` | < 1 s |
| Idle memory excludes transcript bodies | `test_perf_no_transcripts_in_memory` | List query result contains no transcript column |
| One audio in memory at a time | `test_worker_single_audio_in_memory` | Decoder holds ≤ 1 buffer |

Actual measured numbers are recorded in `IMPLEMENTATION_STATUS.md` (addendum §22: *"Record actual benchmark results"*).

## 2. Unit tests (blueprint §23.1)

### WhatsApp parser (`tests/unit/test_parser_*.py`)

| Case | Test | Fixture |
|---|---|---|
| Indonesian format | `test_parse_indonesian` | `14/07/2026, 20.31 - Daniel: PTT-...opus (file attached)` |
| English format | `test_parse_english` | `7/14/26, 8:31 PM - Daniel: PTT-...opus (file attached)` |
| Bracketed timestamp | `test_parse_bracketed` | `[14/07/2026, 20:31:00] Daniel: ...` |
| Dot vs colon separator | `test_parse_time_separators` | `20.31` and `20:31` |
| 12h vs 24h | `test_parse_12h_24h` | `8:31 PM` / `20:31` / `8.31 pm` |
| 2- vs 4-digit year | `test_parse_year_forms` | `14/07/26` and `14/07/2026` |
| UTF-8 BOM | `test_parse_bom` | file starts with `﻿` |
| Hidden Unicode direction marks | `test_parse_lrm_rlm` | `‎` before/inside the header |
| Multiline message | `test_parse_multiline` | continuation lines belong to the previous message |
| System message | `test_parse_system_message` | `Messages and calls are end-to-end encrypted.` → not a voice note |
| Sender name with colon/punctuation | `test_parse_sender_with_colon` | `Dr. Budi: S.Kom: PTT-...opus` |
| Omitted media | `test_parse_media_omitted` | `<Media omitted>` / `<Media tidak disertakan>` → reference **without** filename |
| Duplicate exports | `test_duplicate_export_detection` | same chat exported twice → `duplicate_of_id` set |
| Unparsed header reported safely | `test_unparsed_header_warning` | warning row created; **no private text in the log** |

### Matching (`tests/unit/test_matching_*.py`)

| Case | Test | Asserts |
|---|---|---|
| Exact unique match | `test_match_exact_unique` | confidence `1.00`, `exact_unique`, sender assigned |
| Unique after duplicate-export removal | `test_match_after_dedup` | confidence `0.95`, `exact_duplicate_export_resolved` |
| Ambiguous match | `test_match_ambiguous_stays_ambiguous` | 2 candidates, both kept, **sender = unknown**, record → review |
| Unmatched audio | `test_match_unmatched` | `unmatched`, sender unknown |
| Chat reference with no audio | `test_chat_reference_without_audio` | `chat_reference_without_audio` |
| Below threshold ⇒ no auto-assign | `test_confidence_below_threshold_not_selected` | confidence `0.89` with threshold `0.90` ⇒ **not selected** |
| Timestamp alone never high-confidence | `test_timestamp_alone_never_high_confidence` | timestamp-only evidence caps below `0.90` (addendum §10 final rule) |
| No sender fabrication | `test_no_sender_guessing` | property test: for any input lacking a filename reference, sender is `None` |
| Manual override | `test_manual_override_preserves_original` | override active; **parsed original still readable** |

### Identity / no-repeat / quality / export

| Case | Test |
|---|---|
| SHA-256 fingerprint stability | `test_fingerprint_stable` |
| Same name, different bytes ⇒ different record | `test_same_basename_different_bytes_not_same_file` (addendum §4.7) |
| Changed-source detection | `test_changed_source_creates_new_version` |
| Idempotent scan | `test_rescan_creates_zero_new_records` (addendum §4 final rule) |
| Quality: empty transcript | `test_quality_empty` |
| Quality: repeated-phrase loop | `test_quality_repetition_loop` |
| Quality: long audio, tiny text | `test_quality_long_audio_little_text` |
| Quality: low language probability | `test_quality_low_language_prob` |
| Quality: **short audio is NOT auto-flagged** | `test_quality_short_audio_not_flagged` (blueprint §14 final rule) |
| Markdown formatting + anchors | `test_markdown_format` |
| Markdown determinism | `test_markdown_byte_identical_without_generated_at` |
| Unknown-date isolation | `test_unknown_date_separate_file` |
| TXT formatting | `test_txt_format` |
| CSV UTF-8 BOM | `test_csv_utf8_bom` |
| JSONL validity | `test_jsonl_valid` |
| Atomic export preserves last valid file | `test_atomic_export_failure_preserves_previous` |
| Export count == DB count | `test_export_count_matches_db` |
| Windows-safe filenames | `test_windows_reserved_names`, `test_trailing_dots_spaces`, `test_long_path` |
| Migration manifest validation | `test_manifest_validation` |

### Architecture (enforcement, not convention)

| Test | Asserts |
|---|---|
| `test_no_pyside_in_infrastructure` | `app/database`, `app/models`, `app/parsing`, `app/matching`, `app/exports`, `app/transcription` never import PySide6 |
| `test_no_sql_in_ui` | `app/ui` contains no `sqlite3`, no `execute(` |
| `test_no_engine_in_ui` | `app/ui` never imports `faster_whisper` |
| `test_worker_never_imports_ui` | `worker/` never imports `app.ui` / PySide6 |
| `test_compat_key_not_consulted_in_reuse_check` | `may_reuse()` source contains no `compat_key` |
| `test_no_tanggal_file_label` | i18n resources contain no `Tanggal File` (addendum §14) |
| `test_no_cloud_endpoints` | no `openai`, `api.` transcription endpoints, no telemetry SDK anywhere in `app/` or `worker/` |

## 3. Database tests (blueprint §23.2)

Listed in `DATABASE_MIGRATION_PLAN.md` §7. All 13 are Phase 2 gate items.

## 4. Worker tests (blueprint §23.3)

| Case | Test |
|---|---|
| Model loads | `test_worker_model_loads` |
| Model stays loaded (loaded exactly once) | `test_model_loaded_once` — asserts `model_load_count == 1` after N files |
| One valid audio | `test_worker_transcribes_valid_audio` |
| No speech | `test_worker_no_speech` → state `no_speech`, not `failed` |
| Corrupted audio | `test_worker_corrupted_audio_does_not_stop_queue` |
| Cancellation / pause / safe stop / resume | `test_worker_pause`, `test_worker_resume`, `test_worker_safe_stop` |
| Failure continues queue | `test_worker_failure_continues_queue` |
| Changed source mid-queue | `test_worker_source_changed_midqueue` |
| Completed file skipped | `test_worker_skips_completed` |
| Stale lease recovery | `test_worker_stale_lease_recovery` |
| Duplicate worker blocked | `test_duplicate_worker_prevention` |

Worker tests run against a `FakeEngine` (deterministic, instant) **except** `test_worker_transcribes_valid_audio`, which uses the real faster-whisper Small model on a synthetic generated tone/speech clip. This keeps CI fast while still proving the real engine path.

## 5. UI tests (blueprint §23.4) — `pytest-qt`

first-run wizard · empty database · folder picker · scan · model choice · test run · start · pause · stop · table pagination · filters · edit transcript · manual metadata correction · exports · backup · restore · close-while-active dialog · Indonesian labels present · errors are human-readable (no traceback in the dialog).

## 6. Packaging tests (blueprint §23.5) — Phase 11

| Case | How verified |
|---|---|
| Installer builds | `ISCC.exe` exit 0, artifact exists |
| Install to clean user folder | Install into a temp `%LOCALAPPDATA%` sandbox |
| Launch **without system Python** | Run the built exe with `PATH` scrubbed of every Python dir and `PYTHONHOME`/`PYTHONPATH` cleared; assert the window appears |
| Uninstall | Uninstaller runs; app files gone; **user data still present** |
| Upgrade preserves data | Install v1.0.0 → create DB → install v1.0.1 → DB intact, row counts equal |
| Portable ZIP launch | Extract to a fresh folder, launch, first-run asks for a writable data dir |
| Missing-model flow | Launch with no model → wizard routes to model setup, no crash |
| Model download / import | Import model ZIP offline → verified → usable |
| Release asset checksums | `SHA256SUMS.txt` matches every asset |
| **No private files packaged** | Private-data scanner over the build output: no `.opus`/`.sqlite3`/`.dntbackup`, no `D:\vn` path string, no real phone number/email pattern |

## 7. Limited real-data test (blueprint §23.6, Phase 13) — **max 20 files**

Source: `D:\vn\WhatsApp Voice Notes` (read-only).

Selection (documented, reproducible): very short · medium · longer · clear · noisy · different subfolders · matched metadata · unmatched metadata · duplicate basename if available.

| Verify | Method |
|---|---|
| Transcription produced | non-empty transcript for speech-bearing files |
| Sender / chat / WhatsApp time | manual spot-check against the export |
| Windows created/modified times | stored **separately** from WhatsApp time |
| DB persistence + restart | close app, reopen, records intact |
| No repeat | second run ⇒ 0 new attempts |
| Markdown + TXT | generated, counts match |
| **Source unchanged** | **SHA-256 of all 20 files captured before and after; must be identical** |

**Production (13,126 files) is never started.**

## 8. Test execution commands

```powershell
scripts\test.ps1                 # ruff + mypy + full pytest suite
scripts\test.ps1 -Fast           # skips 13k-record perf + real-model tests
pytest -m "acceptance"           # only the addendum §23–§25 mandatory scenarios
pytest -m "not slow"             # CI pull-request lane
```

Markers: `unit`, `db`, `worker`, `ui`, `acceptance`, `perf`, `slow`, `realmodel`, `realdata`.
`realdata` is **excluded from CI entirely** and only ever runs locally against ≤ 20 files.
