# DIFFERENT NETWORK TRANSCRIBE
## Technical Architecture Addendum

**Purpose:** This addendum supplements `DIFFERENT_NETWORK_TRANSCRIBE_MASTER_BLUEPRINT.md`.  
**Status:** Mandatory clarification for implementation, not a replacement for the master blueprint.  
**Architecture decision:** The original architecture is already sufficient. Do not redesign it from zero. Apply the concrete technical rules below to remove implementation ambiguity.

---

# 1. FINAL ARCHITECTURE DECISION

Use a modular desktop architecture with five layers:

```text
Presentation Layer
PySide6 Desktop UI
        |
Application Layer
Commands, use cases, validation, orchestration
        |
Domain Layer
Audio records, metadata matching, transcript versions, state rules
        |
Infrastructure Layer
SQLite, filesystem, Faster-Whisper, exports, backups
        |
Worker Runtime
Separate local transcription process
```

Rules:

1. UI code must not contain SQL, transcription logic, parser regexes, or filesystem business rules.
2. Database repositories must not import PySide6.
3. The worker must not directly manipulate UI widgets.
4. The domain state machine must be testable without launching the UI.
5. All long operations must run outside the main UI thread.
6. SQLite is the durable authority; UI memory is only a view of current state.
7. Export files are derived artifacts, never the authority.

---

# 2. PROCESS AND IPC CONTRACT

The UI starts one worker subprocess using the packaged worker executable or Python module.

Use a hybrid control design:

- Durable state and progress: SQLite.
- Immediate commands: local command table in SQLite or a local named pipe.
- UI refresh: polling every 500–1,000 ms.
- Worker heartbeat: every 2 seconds.
- Worker lease timeout: 10 seconds by default.
- Progress updates must be rate-limited to avoid excessive database writes.

Required worker commands:

- `start`
- `pause`
- `resume`
- `safe_stop`
- `retry_failed`
- `reprocess_selected`
- `shutdown`

Required worker states:

- `idle`
- `starting`
- `running`
- `pausing`
- `paused`
- `stopping`
- `stopped`
- `failed`

Do not send full transcript bodies through IPC. Store them in SQLite and notify the UI using record IDs.

---

# 3. DATABASE CONCURRENCY RULES

Use one writer principle:

- The transcription worker is the primary processing writer.
- The UI may write user edits and settings through short transactions.
- Exporters may read concurrently.
- Long-running transactions are prohibited.

SQLite configuration:

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```

Rules:

1. Every completed or failed file commits independently.
2. Manual edits use optimistic concurrency with `updated_at` or a revision number.
3. Database migration always creates a backup first.
4. A migration runs inside a transaction when SQLite permits.
5. The app must run `PRAGMA quick_check` on normal startup and `PRAGMA integrity_check` during explicit validation.
6. Use a connection per process. Do not share SQLite connection objects across processes or threads.
7. All timestamps stored in the database use ISO 8601 with timezone when available.
8. Display timestamps in the user’s local timezone.

---

# 4. FILE IDENTITY AND DEDUPLICATION RULES

Use two identifiers:

## Logical audio ID

Represents the same known record inside the application.

## Source-version ID

Represents one exact binary version of a source file.

Recommended identity procedure:

1. Normalize source root.
2. Record relative path.
3. Record file size and modification time.
4. Compute SHA-256.
5. Reuse an existing logical audio record when:
   - SHA-256 matches a known current or historical source version; or
   - the user explicitly confirms a relink.
6. Create a new source version when the same path has a different SHA-256.
7. Never treat matching filename alone as proof that binary audio is identical.

The scanner must be idempotent. Re-running a scan without file changes must produce zero new audio records and zero new transcription jobs.

---

# 5. TRANSCRIPTION COMPATIBILITY KEY

A completed transcript is reusable only when its compatibility key remains valid.

Compatibility key fields:

```text
engine_name
engine_version
model_name
model_artifact_hash
language
task
compute_type
beam_size
temperature
vad_filter
condition_on_previous_text
source_sha256
```

Changing export format, UI theme, folder path, or filename must not invalidate the transcript.

Changing only the model for future files must not requeue completed files.

Completed files are reprocessed only when:

- the user explicitly requests reprocessing;
- the source SHA-256 changed;
- the transcript is marked invalid;
- the selected attempt was corrupted or missing from SQLite;
- a migration explicitly changes transcript semantics.

---

# 6. MODEL MANAGEMENT

Create a model registry.

Each model record stores:

- display name;
- engine model identifier;
- local folder;
- expected size;
- artifact manifest;
- SHA-256 checksums where available;
- installed state;
- verification state;
- last verified time;
- minimum RAM recommendation.

Model installation behavior:

1. Never download silently.
2. Show expected disk use.
3. Download to a temporary `.partial` location.
4. Verify all required files.
5. Atomically rename into the final model folder.
6. Preserve the previous valid model if an update fails.
7. Support offline model import from ZIP.
8. Do not place model weights in normal Git history.

The worker must fail gracefully when a chosen model is unavailable and return the user to model setup.

---

# 7. SMALL AND MEDIUM USER EXPERIENCE

Before the first production run:

- Small is selected by default.
- Medium is available as a deliberate choice.
- The user sees an estimated relative speed warning, not a guaranteed duration.

After production begins:

- The selected default model applies to pending files.
- Existing completed files remain unchanged.
- Reprocessing completed files requires explicit selection and confirmation.

Recommended message:

> Model baru hanya digunakan untuk file yang belum selesai. File yang sudah selesai tidak akan diulang kecuali Anda memilihnya secara manual.

---

# 8. AUDIO DECODING AND TEMPORARY FILE POLICY

Use PyAV directly whenever possible.

If conversion is required:

1. Create a unique temporary directory per processing session.
2. Never write beside the original audio.
3. Use a generated filename unrelated to private sender names.
4. Delete temporary files after success or failure.
5. Clean stale temporary files older than a configurable threshold during startup.
6. Never delete outside the application Temp directory.

Audio duration and stream information must be read before transcription where possible.

---

# 9. WHATSAPP PARSER VERSIONING

Parser behavior must be versioned.

Store:

- parser version;
- matched pattern ID;
- normalized header hash;
- parse warning;
- confidence.

When parser rules improve:

1. Reparse chat exports.
2. Preserve previous parse results until the new run succeeds.
3. Recompute metadata matches.
4. Do not retranscribe audio.
5. Preserve manual metadata overrides.

Parsing and transcription are independent pipelines.

---

# 10. MATCH CONFIDENCE RULES

Use explicit confidence values:

- `1.00`: unique exact filename match.
- `0.95`: unique match after duplicate-export removal.
- `0.70–0.89`: supported by multiple consistent clues.
- `<0.70`: do not auto-select.

Automatic sender assignment is allowed only when confidence is at or above a configurable threshold, default `0.90`.

Below threshold:

- sender remains unknown;
- candidate list is preserved;
- record enters review.

File timestamps alone must never produce a high-confidence sender match.

---

# 11. TRANSCRIPT VERSION RULES

Every transcript version is immutable after creation.

Types:

- model raw;
- model normalized;
- manual correction;
- imported correction.

A new manual edit creates a new version. It does not overwrite the previous manual version.

Preferred transcript selection must be stored explicitly.

Required audit fields:

- version creator type;
- created time;
- based-on version;
- selected-as-preferred time;
- optional note.

---

# 12. MARKDOWN EXPORT CONTRACT

Default second-brain output:

```text
Output/Markdown/Daily/YYYY/YYYY-MM/YYYY-MM-DD.md
```

Use deterministic record anchors:

```markdown
<a id="dnt-<stable-id>"></a>
```

Default metadata must stay concise.

Do not include:

- SHA-256;
- technical engine settings;
- database IDs;
- full error history;
- Windows timestamps;

unless `Sertakan metadata teknis` is enabled.

Required daily ordering:

1. Valid WhatsApp timestamps in chronological order.
2. Same-time records ordered by stable ID.
3. Unknown-time records in `Unknown-Date.md`.

Markdown export must be deterministic: the same database state and settings must produce byte-identical output except for an explicitly included generation timestamp.

Provide an option to omit `generated_at` so second-brain files do not change on every export.

---

# 13. OUTPUT NAMING AND COLLISION RULES

Never rely on basename alone.

Individual output filename:

```text
<whatsapp-date-or-unknown>__<normalized-basename>__<short-stable-id>.md
```

Example:

```text
2026-07-14__PTT-20260714-WA0043__a81f29c2.md
```

Use Windows-safe filename normalization.

Handle:

- reserved names such as `CON`, `PRN`, `AUX`, `NUL`;
- trailing spaces and dots;
- long paths;
- duplicate basenames;
- Unicode names.

Enable long-path-safe logic and keep generated path lengths reasonably short.

---

# 14. WINDOWS-SPECIFIC FILE-TIME RULES

On Windows:

- creation time is filesystem metadata, not proof of original WhatsApp message time;
- copying files may change creation time;
- modification time may be preserved or altered depending on the copy method.

The UI and export must label them exactly:

- `Timestamp WhatsApp`
- `File dibuat di Windows`
- `File diubah di Windows`

Never display a generic `Tanggal File` label.

---

# 15. APPLICATION CONFIGURATION

Use a versioned configuration file in the user data folder.

Recommended format: TOML.

Configuration categories:

- paths;
- transcription defaults;
- CPU preset;
- UI;
- export;
- backup;
- privacy;
- diagnostics.

Rules:

1. Validate config before use.
2. Keep a last-known-good copy.
3. Back up before migration.
4. Unknown fields should be preserved when possible.
5. Secrets are not expected in v1.
6. Never store private transcript bodies in config.

---

# 16. OBSERVABILITY

Use structured local logging.

Log levels:

- INFO: lifecycle and counts.
- WARNING: recoverable issue.
- ERROR: failed operation.
- DEBUG: technical details, disabled by default.

Required identifiers:

- session ID;
- worker ID;
- audio stable ID;
- attempt ID;
- export ID.

Do not log full transcript text by default.

Create a user-readable diagnostics bundle containing:

- sanitized logs;
- app version;
- OS version;
- database schema version;
- dependency versions;
- model manifest;
- configuration without private paths when possible;
- latest integrity report.

Do not include audio, chat exports, or transcripts unless the user explicitly selects them.

---

# 17. FAILURE DOMAINS

Handle these independently:

- scanner failure;
- parser failure;
- matching failure;
- model setup failure;
- audio decode failure;
- transcription failure;
- database failure;
- export failure;
- backup failure;
- installer failure.

A failure in one domain must not incorrectly mark unrelated records failed.

Example:

- export failure must not invalidate successful transcripts;
- parser improvement must not trigger transcription;
- missing source must not delete database transcript history.

---

# 18. BACKUP CONSISTENCY

Before copying a live SQLite database:

- use SQLite backup API; or
- checkpoint WAL and use a safe backup mechanism.

Do not copy only the main `.sqlite3` file while ignoring active WAL state.

Backup manifest must include:

- database SHA-256;
- schema version;
- app version;
- creation time;
- included components;
- model manifests;
- export manifests.

Restore must use staging and integrity validation before replacing active data.

---

# 19. INSTALLER AND PORTABLE BUILD RULES

## Installed build

- application files under `%LOCALAPPDATA%\Programs\Different Network Transcribe`;
- user data elsewhere;
- upgrades preserve user data;
- uninstaller does not remove user data by default.

## Portable build

Portable ZIP contains:

- application runtime;
- no private database;
- no source audio;
- no transcript;
- no personal config;
- optional Small model only if release size allows.

On first portable launch, ask for a writable data directory.

Do not write persistent data inside a read-only or protected application directory.

---

# 20. RELEASE REPRODUCIBILITY

Every release must record:

- Git commit;
- version;
- Python version;
- dependency lock hash;
- PyInstaller version;
- Inno Setup version;
- model manifest hash;
- build timestamp;
- SHA-256 for every asset.

Release assets must be built from a clean checkout.

The release workflow must fail when:

- tests fail;
- asset checksum generation fails;
- private test data is detected;
- installer smoke test fails;
- an asset exceeds GitHub’s release limit.

---

# 21. PRIVATE-DATA EXCLUSION

Add `.gitignore` and release scanning rules for:

```text
*.opus
*.ogg
*.mp3
*.wav
*.m4a
*.aac
*.flac
*.webm
*.mp4
*.sqlite
*.sqlite3
*.db
*.dntbackup
Output/
Logs/
Backups/
Models/
Temp/
real-fixtures/
```

Use synthetic fixtures in the repository.

Before building release assets, run a private-data scanner that checks for:

- real phone numbers;
- real email addresses;
- production database files;
- transcript output folders;
- WhatsApp media files;
- user-specific absolute paths.

---

# 22. PERFORMANCE ACCEPTANCE THRESHOLDS

For a synthetic database with 13,000 records on a normal development machine:

- app startup to usable dashboard: target under 5 seconds excluding first model setup;
- first table page: target under 1 second;
- normal paginated query: target under 500 ms;
- filter/search query: target under 1 second for indexed fields;
- UI refresh must not block interaction;
- memory use at idle should remain reasonable and not include all transcript bodies;
- only one audio is loaded for transcription at a time by default.

These are engineering targets, not absolute user guarantees. Record actual benchmark results.

---

# 23. ACCEPTANCE TEST FOR NO-REPEAT

Mandatory automated scenario:

1. Scan 20 synthetic/real test files.
2. Transcribe them.
3. Record attempt count.
4. Restart the app.
5. Scan again.
6. Start transcription again.
7. Verify:
   - zero new attempts for unchanged successful files;
   - zero model inference for those files;
   - completed count unchanged;
   - skip events recorded.
8. Delete generated MD/TXT.
9. Export again.
10. Verify no transcription attempt was added.
11. Move source files.
12. Relink by fingerprint.
13. Verify no transcription attempt was added.

---

# 24. ACCEPTANCE TEST FOR SAFE STOP

Mandatory scenario:

1. Queue at least five files.
2. Start worker.
3. Request safe stop during file two.
4. Verify:
   - file one remains complete;
   - file two is either complete or safely requeued;
   - files three to five remain pending;
   - database integrity passes;
   - worker lease is released;
   - restart continues without duplicating file one.

---

# 25. ACCEPTANCE TEST FOR MODEL CHANGE

Mandatory scenario:

1. Complete records using Small.
2. Change default model to Medium.
3. Start processing.
4. Verify completed Small records are not reprocessed.
5. Add a new file.
6. Verify the new file uses Medium.
7. Explicitly select one Small record for Medium reprocessing.
8. Verify both attempts remain stored and preferred selection is correct.

---

# 26. FINAL INSTRUCTION TO THE CODING AGENT

Do not redesign the master architecture. It is already sufficient.

Use this addendum to make implementation decisions concrete.

Before writing production code, produce:

1. final component diagram;
2. database migration plan;
3. worker IPC contract;
4. model registry format;
5. transcript compatibility-key definition;
6. export format examples;
7. packaging matrix;
8. test matrix mapped to every mandatory acceptance test.

Then implement the existing master blueprint phase by phase.

Do not start the full production transcription.
