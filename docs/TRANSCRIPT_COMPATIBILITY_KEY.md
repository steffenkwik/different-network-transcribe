# Transcript Compatibility Key

Implements `TECHNICAL_ADDENDUM.md` §5 and §26 deliverable 5.

This is the most safety-critical definition in the project. Getting it wrong means either **retranscribing 13,000 files by accident** or **serving a stale transcript for a file whose audio changed**.

---

## 1. Definition

```text
compat_key = SHA-256( canonical_json({
    "engine_name":               "faster-whisper",
    "engine_version":            "1.1.1",
    "model_name":                "small",
    "model_artifact_hash":       "<sha256 of model.bin>",
    "language":                  "id",
    "task":                      "transcribe",
    "compute_type":              "int8",
    "beam_size":                 5,
    "temperature":               0.0,
    "vad_filter":                true,
    "condition_on_previous_text": false,
    "source_sha256":             "<sha256 of the audio file bytes>"
}) )
```

`canonical_json` = keys sorted, no whitespace, UTF-8, floats formatted with `repr()`. The key is computed once when an attempt is created and stored on `transcription_attempts.compat_key`.

The 11 fields are exactly the addendum §5 list. Nothing added, nothing removed.

## 2. What the key IS for

The key answers one question:

> **"Was this stored transcript produced by the same engine + model + settings + audio bytes that I would use right now?"**

It is used to:
- label a transcript in the UI: *"Transkrip ini dibuat dengan pengaturan berbeda"* (informational);
- let the user find transcripts eligible for refresh and **explicitly** select them;
- record provenance in attempt history and diagnostics.

## 3. What the key is **NOT** for — the critical rule

> ### A compat-key mismatch NEVER automatically requeues a completed file.

This is the single most important rule in the no-repeat guarantee, and it is easy to get wrong. A naive implementation writes:

```python
if attempt.compat_key != current_compat_key():   # ← WRONG. DO NOT DO THIS.
    requeue(audio_file)
```

That code would retranscribe all 13,000 completed files the moment the user nudges `beam_size` in Advanced Settings, or upgrades faster-whisper, or switches the default model to Medium. The blueprint forbids exactly this (§13, §7.3: *"Changing the default model affects pending/new files only"*; addendum §5: *"Changing only the model for future files must not requeue completed files"*).

**`source_sha256` is the only field in the key that has requeue authority**, and it is checked directly — not via the key.

## 4. The actual reprocess triggers (closed list — addendum §5)

A **completed** file gets a new transcription attempt if and only if one of these is true:

| # | Trigger | Detected by |
|---|---|---|
| 1 | The user explicitly requests reprocessing | `worker_commands.command = 'reprocess_selected'` |
| 2 | The source SHA-256 changed | scanner: on-disk sha ≠ `audio_source_versions.sha256` where `is_current=1` |
| 3 | The transcript is marked invalid | `audio_files.current_state = 'invalid_output'` or the preferred attempt flagged invalid |
| 4 | The selected attempt is corrupted or missing from SQLite | integrity check: `preferred_transcript_id` dangling, or `raw_transcript IS NULL` on a `completed` attempt |
| 5 | A migration explicitly changes transcript semantics | migration sets a documented `force_reprocess` marker; no migration in v1 does this |

Everything else — export format, UI theme, folder path, filename, default-model change, beam size, thread preset, parser upgrade, app upgrade — **must not** invalidate a transcript.

## 5. Explicit non-triggers (each has a test)

| Change | Requeues? | Test |
|---|---|---|
| Export format / options changed | ❌ No | `test_export_settings_change_does_not_requeue` |
| UI theme changed | ❌ No | `test_ui_settings_change_does_not_requeue` |
| Audio file **moved** (same bytes) | ❌ No — relink by fingerprint | `test_move_and_relink_no_new_attempt` |
| Audio file **renamed** (same bytes) | ❌ No | `test_rename_no_new_attempt` |
| Default model Small → Medium | ❌ No for completed; ✅ new/pending files use Medium | `test_model_change_does_not_reprocess_completed` (addendum §25) |
| `beam_size` / `temperature` changed | ❌ No | `test_advanced_settings_change_does_not_requeue` |
| faster-whisper version upgraded | ❌ No | `test_engine_upgrade_does_not_requeue` |
| Parser improved, chats reparsed | ❌ No — metadata only | `test_reparse_does_not_touch_attempts` |
| Generated `.md`/`.txt` deleted | ❌ No — rebuild from SQLite | `test_deleted_output_regenerates_without_transcription` (addendum §23.8–10) |
| Audio file **content** changed | ✅ Yes — new source version | `test_changed_source_creates_new_version` |
| User clicks "Proses Ulang dengan Medium" | ✅ Yes — both attempts preserved | `test_explicit_reprocess_preserves_both_attempts` |

## 6. Preferred-transcript selection (blueprint §7.4)

The compat key never selects the preferred transcript. This priority order does, and it is stored explicitly in `audio_files.preferred_transcript_id`:

```text
1. verified manual correction          (manual_transcripts.verified = 1, active = 1)
2. manually selected Medium attempt    (user chose it)
3. successful Medium attempt for a flagged record
4. successful Small attempt
```

Medium is **never** automatically declared superior. Both results are preserved and both are visible in the detail drawer (blueprint §7.4: *"Do not automatically declare Medium superior without preserving and reviewing both results"*).

## 7. Reuse check, in code terms

```python
def may_reuse(audio: AudioFile, on_disk_sha: str) -> bool:
    """True ⇒ SKIP transcription. Implements blueprint §13."""
    if not audio.source_exists:
        return False                                  # missing_source (not a reuse)
    if on_disk_sha != audio.current_source_version.sha256:
        return False                                  # trigger 2: source changed
    attempt = audio.preferred_attempt
    if attempt is None or attempt.state != "completed":
        return False
    if attempt.raw_transcript is None:
        return False                                  # trigger 4: corrupted/missing
    if audio.current_state == "invalid_output":
        return False                                  # trigger 3
    if audio.has_pending_reprocess_request:
        return False                                  # trigger 1
    return True                                       # ← compat_key is NOT consulted here
```

The absence of `compat_key` from this function is deliberate and is asserted by `test_compat_key_not_consulted_in_reuse_check`, which reads the source of `may_reuse` and fails if `compat_key` appears in it. That test exists specifically to stop a future contributor from "fixing" this function into a 13,000-file retranscription.
