# DIFFERENT NETWORK TRANSCRIBE
## Master Product Blueprint, Technical Blueprint, Build Plan, and Coding-Agent Specification

**Document status:** Authoritative project specification  
**Target version:** v1.0  
**Prepared for:** Different Network internal team  
**Primary coding-agent target:** Claude Code, Codex, GitHub Copilot Agent, or equivalent repository-aware coding agent  
**Target operating system:** Windows 10/11 x64  
**Last updated:** 2026-07-14  

---

# 0. HOW THE CODING AGENT MUST USE THIS FILE

This file is the single source of truth for the project.

The coding agent must:

1. Read this file completely before editing or creating code.
2. Treat all requirements marked **MUST**, **MUST NOT**, and **Definition of Done** as mandatory.
3. Build the product in the phases defined in this document.
4. Keep an implementation checklist and update it after each phase.
5. Run tests and show evidence before claiming a phase is complete.
6. Never start the complete production transcription of approximately 13,000 files.
7. Use no more than 20 real audio files for integration testing.
8. Never upload private audio, chat exports, names, or transcripts to a cloud service.
9. Produce a Windows installer and a portable ZIP release.
10. Stop after the application is built, tested, packaged, and audited.

The finished product must run independently after the coding-agent session is closed. Production transcription must not consume Claude Code, Codex, Copilot, ChatGPT, or API usage.

---

# 1. EXECUTIVE DECISION

Build a local Windows desktop application named:

# **Different Network Transcribe**

Its purpose is to:

- scan large collections of WhatsApp voice notes;
- transcribe them locally;
- connect each voice note with sender, chat, and WhatsApp timestamp when the exported chat contains sufficient metadata;
- preserve Windows file timestamps separately;
- prevent successful files from being transcribed repeatedly;
- resume safely after interruption;
- export results as Markdown and plain text for a second-brain workflow;
- remain simple enough for nontechnical internal team members;
- be distributed through GitHub as source code, a portable ZIP, and a Windows installer.

## Final recommended technology

### Application

- Python 3.12.x for development and runtime bundling.
- PySide6 Qt Widgets for the desktop interface.
- SQLite for durable local state.
- Faster-Whisper for local transcription.
- PyAV for local audio decoding.
- One dedicated transcription worker process.
- PyInstaller one-folder packaging for predictable handling of native dependencies.
- Inno Setup for the final Windows installer.
- GitHub Actions for tests and release builds.

### Default model strategy

- **Small:** default and recommended for the first 13,000 files.
- **Medium:** selectable before the first production run when accuracy is more important than speed.
- Medium may also be used later for explicitly selected or quality-flagged files.
- The application must never silently retranscribe all completed Small files with Medium.

### Default runtime strategy

- CPU with `int8` compute for maximum Windows compatibility.
- The application architecture must allow another backend later, but v1 must not depend on experimental AMD GPU setup.
- The model must remain loaded in one long-running worker while processing the queue. Do not reload the model for every voice note.

## Why this stack

Faster-Whisper officially supports CPU `int8`, decodes audio through PyAV without requiring a separately installed FFmpeg application, and publishes CPU benchmarks showing materially lower processing time and memory than the original OpenAI Whisper implementation. Its official documentation currently describes NVIDIA CUDA for GPU execution, so CPU mode is the reliable cross-computer default for this Windows/AMD use case.

PySide6 is the official Qt binding for Python and is suitable for a polished Windows desktop application. The end user will not install Python because the packaged release includes the runtime.

SQLite is appropriate because the application is local, must be resumable, must preserve history, and must support thousands of searchable records without a server.

## Important truth about Markdown

`.md` and `.txt` are both plain-text formats. Markdown is not automatically lower-token merely because the file extension is `.md`. Markdown is better for the second brain because it provides consistent headings, metadata, links, and machine-readable front matter. The exporter must avoid decorative text and duplicated metadata to keep AI ingestion efficient.

---

# 2. PRODUCT SCOPE

## 2.1 In scope for v1.0

The application MUST provide:

1. Local-only transcription.
2. Recursive audio-folder scanning.
3. Recursive WhatsApp-export TXT scanning.
4. Sender, chat, and WhatsApp timestamp matching when metadata permits.
5. Windows file creation and modification timestamps.
6. Permanent SQLite tracking.
7. Small or Medium model selection.
8. Safe start, pause, stop, and resume.
9. No-repeat logic.
10. Quality flags.
11. Manual transcript correction.
12. Manual sender/chat/timestamp correction.
13. Audio playback.
14. Search and filters.
15. Markdown export.
16. TXT export.
17. CSV and JSONL technical exports.
18. Backups.
19. Migration to another computer.
20. GitHub source repository.
21. GitHub portable ZIP.
22. GitHub Windows installer.
23. Automatic dependency setup through the installer.
24. First-run model setup.
25. A simple Indonesian user interface and help guide.

## 2.2 Explicitly out of scope for v1.0

Do not add these unless all mandatory v1 requirements are complete:

- cloud synchronization;
- web application;
- mobile application;
- multi-user accounts;
- team permissions;
- remote database;
- browser extension;
- automatic WhatsApp login;
- direct WhatsApp scraping;
- biometric speaker identification;
- speaker recognition based on voice identity;
- live meeting transcription;
- automatic summarization using cloud AI;
- automatic upload to a second-brain service;
- complicated plugin architecture;
- automatic internet updater;
- many visual themes;
- dashboards with decorative analytics;
- unrelated media-management functions.

---

# 3. USER PROFILES AND DESIGN PRINCIPLES

## Primary user

A nontechnical Windows user who wants to:

- choose folders;
- scan files;
- choose Small or Medium;
- test a small sample;
- start transcription;
- see progress;
- stop safely;
- resume later;
- review unclear records;
- export Markdown or TXT;
- move the application data to another computer.

## Internal team member

A team member who downloads the installer or portable ZIP from GitHub and expects the application to work without installing Python or running terminal commands.

## Design principles

1. **Simple before clever.**
2. **Reliable before visually impressive.**
3. **No hidden destructive behavior.**
4. **No guessing sender identity.**
5. **No unnecessary retranscription.**
6. **Every important action has a confirmation or visible result.**
7. **Advanced settings remain hidden unless needed.**
8. **The database is the source of truth.**
9. **Source files are read-only.**
10. **The user sees Indonesian language; logs may use English.**

---

# 4. USER EXPERIENCE FROM INSTALLATION TO DAILY USE

## 4.1 First installation

The teammate opens:

`DifferentNetworkTranscribe-Setup-x64.exe`

The installer:

1. Installs the application per user by default.
2. Includes all application dependencies.
3. Creates a Start Menu shortcut.
4. Optionally creates a Desktop shortcut.
5. Does not require a separate Python installation.
6. Does not delete user data during update or uninstall without explicit confirmation.
7. Opens the application at the end if selected.

## 4.2 First-run wizard

### Step 1 — Welcome

Display:

> Different Network Transcribe memproses audio secara lokal di komputer ini.  
> Audio dan transkrip tidak dikirim ke cloud.

### Step 2 — Select data location

Default:

`%USERPROFILE%\Documents\Different Network Transcribe Data`

Allow another local folder or external drive.

Data folder structure:

```text
Different Network Transcribe Data/
├── Database/
├── Models/
├── Output/
│   ├── Markdown/
│   ├── Text/
│   ├── CSV/
│   ├── JSONL/
│   ├── Individual/
│   └── Reports/
├── Backups/
├── Logs/
├── Temp/
└── Config/
```

Do not store the database, models, outputs, or private data under Program Files.

### Step 3 — Select input folders

The wizard asks for:

- one or more audio folders;
- one or more exported-chat folders.

The user may add or remove source folders later.

### Step 4 — Choose transcription model

Show only two simple options:

#### Small — Cepat, direkomendasikan

- recommended for the initial 13,000 files;
- lower processing time;
- good general Indonesian transcription;
- lower disk and memory requirements.

#### Medium — Lebih akurat, lebih lambat

- recommended when accuracy matters more than time;
- higher disk and memory requirements;
- substantially slower than Small.

Default selection: **Small**.

Provide a small explanation, not a technical wall of text.

### Step 5 — Install or verify model

The application:

1. Detects whether the selected model exists.
2. Shows download size before downloading.
3. Downloads from a versioned trusted model source or imports an offline model pack.
4. Displays progress.
5. Verifies SHA-256.
6. Stores the model in the data folder.
7. Never silently downloads Medium.

### Step 6 — Initial scan

Show:

- number of audio files discovered;
- number of export-chat files;
- duplicate filename count;
- unreadable/zero-byte count;
- exact metadata match count;
- ambiguous match count;
- unmatched count.

### Step 7 — Test

Offer:

`Tes Maksimal 20 VN`

The test must not start production.

### Step 8 — Finish

Display:

> Different Network Transcribe siap digunakan.

## 4.3 Initial 13,000-file workflow

1. Install and launch.
2. Choose data and input folders.
3. Select Small or Medium.
4. Scan.
5. Test up to 20 representative voice notes.
6. Review audio, sender, timestamp, and transcript.
7. Click `Mulai Transkripsi`.
8. Leave the worker running.
9. Pause or stop safely when needed.
10. Resume later without restarting completed work.
11. Export Markdown/TXT whenever desired.

## 4.4 Routine future workflow

1. Copy new voice notes into an existing or new source folder.
2. Add newer exported-chat TXT files.
3. Open the application.
4. Click `Scan File Baru`.
5. Click `Mulai / Lanjutkan`.
6. Only new, changed, failed-retry, or manually selected records are processed.
7. Existing valid transcripts remain untouched.
8. Export updated second-brain files.

---

# 5. SIMPLE UI BLUEPRINT

Use one main window and four navigation sections.

## 5.1 Beranda

### Summary cards

- Total VN
- Selesai
- Belum Diproses
- Perlu Diperiksa
- Gagal
- Pengirim Tidak Diketahui

### Progress area

- overall progress bar;
- percentage;
- current file;
- sender and chat when known;
- selected model;
- files completed this session;
- elapsed time;
- estimated remaining time only after sufficient samples;
- application status.

### Primary actions

- `Scan File Baru`
- `Tes Maksimal 20 VN`
- `Mulai / Lanjutkan`
- `Jeda`
- `Berhenti Aman`
- `Buat Hasil`
- `Buka Folder Hasil`

The main primary button is `Mulai / Lanjutkan`.

Disable actions that are not valid in the current state.

## 5.2 Semua Transkrip

Use database pagination. Never load all transcript bodies at startup.

Columns:

- Status
- Pengirim
- Chat
- Timestamp WhatsApp
- Nama File
- Durasi
- Model
- Kualitas
- Terakhir Diproses

Functions:

- search by filename;
- search by sender;
- search by chat;
- explicit transcript text search;
- filter by status;
- filter by quality;
- filter by model;
- filter by metadata-match state;
- date range;
- sort.

### Detail drawer or dialog

Show normal fields first:

- sender;
- chat;
- WhatsApp timestamp;
- filename;
- duration;
- source path;
- selected/preferred transcript;
- model;
- quality;
- attempt count.

Show technical fields only in an expandable section:

- fingerprint;
- file size;
- Windows created/modified times;
- discovery time;
- processing start/end;
- language probability;
- decoding settings;
- attempt history.

Actions:

- Putar Audio
- Berhenti Memutar
- Buka Lokasi File
- Edit Transkrip
- Simpan Koreksi
- Pulihkan Versi
- Proses Ulang dengan Small
- Proses Ulang dengan Medium
- Tandai Benar
- Tandai Perlu Diperiksa

## 5.3 Perlu Diperiksa

Collect:

- failed decoding;
- no speech;
- suspicious transcript;
- ambiguous sender;
- unknown sender;
- missing WhatsApp timestamp;
- changed source;
- missing output;
- manual-review flag.

Support multi-selection for:

- retry;
- Medium reprocessing;
- mark verified;
- export review list.

For manual metadata correction:

- keep original parsed metadata;
- store corrected sender/chat/timestamp separately;
- use manual values in preferred export;
- show that values were manually corrected.

## 5.4 Pengaturan & Data

### Basic settings

- audio source folders;
- chat-export folders;
- data folder;
- default model: Small or Medium;
- language: Indonesia or Automatic;
- CPU usage: Rendah / Seimbang / Maksimal;
- retry limit;
- light/dark/system theme.

### Data actions

- Scan File Baru
- Cocokkan Ulang Metadata
- Unduh/Impor Model
- Backup Sekarang
- Pulihkan Backup
- Buat Paket Pindah Komputer
- Pulihkan Paket
- Periksa Integritas
- Buka Folder Data
- Buka Log Masalah

### Advanced settings

Collapsed by default:

- beam size;
- VAD;
- temperature;
- worker count;
- CPU threads;
- export grouping;
- output naming pattern.

---

# 6. SYSTEM ARCHITECTURE

## 6.1 High-level design

```text
PySide6 Desktop UI
        |
        | starts, pauses, stops, queries status
        v
Dedicated Transcription Worker Process
        |
        +--> Faster-Whisper model kept loaded
        +--> PyAV audio decoding
        +--> Quality checks
        +--> Atomic output generation
        |
        v
SQLite Database (source of truth)
        |
        +--> Markdown exporter
        +--> TXT exporter
        +--> CSV exporter
        +--> JSONL exporter
        +--> backup and migration
```

## 6.2 Why a separate worker process

The UI must not run transcription on the main thread.

The worker process provides:

- responsive interface;
- safe stop;
- independent memory lifecycle;
- clear crash recovery;
- prevention of UI lockups;
- model loaded once;
- clean separation between control and processing.

## 6.3 Worker ownership and locking

Only one production worker may operate on a database.

Use:

- database worker lease;
- process ID;
- heartbeat timestamp;
- instance token.

If a valid worker is already running, show:

> Proses transkripsi sudah berjalan.

If the lease is stale after a crash, recovery must requeue only interrupted records.

## 6.4 Communication

The UI should not parse console text as the authoritative status.

Use:

- SQLite state for durable progress;
- a local IPC channel or structured status file for immediate updates;
- periodic UI polling at a reasonable interval;
- a worker-control table or named pipe for pause/stop commands.

No internet service and no local web server are required.

---

# 7. TRANSCRIPTION ENGINE AND MODEL STRATEGY

## 7.1 Engine

Use Faster-Whisper with pinned compatible versions.

Requirements:

- CPU `int8`;
- one model instance;
- one audio at a time by default;
- configurable thread count;
- model loaded once per worker session;
- segments fully consumed before marking complete;
- explicit Indonesian language by default;
- task `transcribe`, never `translate`.

## 7.2 Recommended settings

```toml
[transcription]
default_model = "small"
review_model = "medium"
language = "id"
task = "transcribe"
device = "cpu"
compute_type = "int8"
beam_size = 5
temperature = 0.0
vad_filter = true
condition_on_previous_text = false
workers = 1
```

CPU threads must be selected automatically from hardware, with user presets:

- Rendah: approximately 40% logical threads.
- Seimbang: approximately 65–75%.
- Maksimal: approximately 85–90%, leaving enough responsiveness for Windows.

Do not hardcode the current user's CPU.

## 7.3 Small versus Medium behavior

### Before initial production

The user chooses Small or Medium.

### After completed records exist

Changing the default model affects pending/new files only.

The application must show:

> Mengubah model default tidak akan mengulang file yang sudah selesai.

To reprocess old files, the user must explicitly select them.

### Model history

Every attempt stores:

- model name;
- model artifact hash/version;
- engine version;
- settings;
- start/end;
- result;
- failure;
- quality metrics.

Do not overwrite previous attempts.

## 7.4 Accuracy strategy

No model is guaranteed to be perfect.

Practical strategy:

1. Use Small for all initial files when speed matters.
2. Flag suspicious results.
3. Reprocess selected important/flagged records using Medium.
4. Preserve both results.
5. Allow a human correction.
6. Preferred transcript priority:
   - verified manual correction;
   - manually selected Medium;
   - successful Medium for a flagged record;
   - successful Small.

Do not automatically declare Medium superior without preserving and reviewing both results.

## 7.5 Optional future acceleration

The code must define a transcription-engine interface so another backend can be added later.

Do not delay v1 for:

- AMD ROCm;
- Vulkan;
- CUDA;
- DirectML;
- OpenVINO.

A later release may benchmark `whisper.cpp` Vulkan on AMD. V1 reliability must not depend on it.

---

# 8. AUDIO DISCOVERY

## 8.1 Supported inputs

Recursively detect:

- `.opus`
- `.ogg`
- `.mp3`
- `.wav`
- `.m4a`
- `.aac`
- `.flac`
- `.webm`
- `.mp4`

## 8.2 Source safety

Input folders are read-only from the application's perspective.

The application MUST NOT:

- delete;
- rename;
- move;
- overwrite;
- edit;
- convert in place.

## 8.3 File metadata

Record:

- absolute path;
- source-root ID;
- relative path;
- basename;
- extension;
- parent folder;
- file size;
- Windows creation time;
- Windows modification time;
- first discovery time;
- last seen time;
- readable state;
- audio duration;
- full SHA-256;
- duplicate-basename group;
- source version.

## 8.4 Identity

Use a stable source version identity based on:

- source-root identity;
- normalized relative path;
- size;
- modification timestamp;
- SHA-256.

SHA-256 is the final authority when paths change.

## 8.5 Move and relink

If a source path changes but a fingerprint matches:

- relink the existing record;
- preserve transcript state;
- do not retranscribe;
- record path history.

---

# 9. WHATSAPP EXPORT PARSING AND METADATA MATCHING

## 9.1 Important limitation

The application cannot reliably identify the sender from audio alone.

Sender, chat, and WhatsApp timestamp are derived from WhatsApp export metadata.

If the export includes a referenced media filename, exact matching can be strong.

If an export only says `<Media omitted>` or `<Media tidak disertakan>` without the filename, exact mapping may be impossible. The application must never claim certainty that the data does not support.

## 9.2 Input

Read all `.txt` files recursively from selected chat-export folders.

## 9.3 Supported patterns

Examples:

```text
14/07/2026, 20.31 - Daniel: PTT-20260714-WA0043.opus
14/07/2026, 20:31 - Daniel: PTT-20260714-WA0043.opus
[14/07/2026, 20:31:00] Daniel: PTT-20260714-WA0043.opus
```

Support:

- Indonesian and English wording;
- dot/colon time separator;
- 12-hour and 24-hour time;
- two/four-digit year;
- UTF-8 BOM;
- hidden Unicode direction marks;
- multiline messages;
- system messages;
- group and private chats;
- sender names with punctuation or colons;
- duplicate chat exports;
- attachment/omitted-media phrases.

## 9.4 Parsed record

Store:

- chat export ID;
- source file;
- inferred chat title;
- line/record number;
- message timestamp;
- sender;
- referenced media filename;
- parser pattern;
- parser version;
- confidence;
- warning;
- normalized raw header hash.

Do not store unrelated chat body content unless needed for message-boundary parsing.

## 9.5 Match states

- `exact_unique`
- `exact_duplicate_export_resolved`
- `exact_ambiguous`
- `filename_not_present`
- `chat_reference_without_audio`
- `probable_timestamp_match`
- `unmatched`
- `manually_resolved`

## 9.6 Matching order

1. Exact normalized basename.
2. Remove duplicate copies of the same exported chat.
3. Compare chat source and path context.
4. Use timestamps only as supporting evidence.
5. If still ambiguous, keep all candidates and mark unknown.
6. Never fabricate sender/chat/time.

## 9.7 Manual correction

Manual correction stores:

- corrected sender;
- corrected chat;
- corrected timestamp;
- user correction time;
- optional note;
- original candidates.

Exports use manual preferred metadata but preserve parsed originals.

---

# 10. TIMESTAMP MODEL

These fields must never be conflated:

1. `whatsapp_message_at`
2. `windows_created_at`
3. `windows_modified_at`
4. `first_discovered_at`
5. `last_scanned_at`
6. `transcription_started_at`
7. `transcription_completed_at`
8. `last_attempt_at`
9. `last_exported_at`
10. `last_validated_at`

If WhatsApp timestamp is unknown, display:

> Timestamp WhatsApp tidak diketahui

Never substitute a filesystem time and label it as WhatsApp time.

---

# 11. DATABASE BLUEPRINT

Use SQLite in WAL mode where appropriate.

Database:

`Database/different_network_transcribe.sqlite3`

## 11.1 Required tables

### `app_schema_migrations`

- version
- name
- applied_at
- checksum

### `source_roots`

- id
- kind (`audio`, `chat`)
- original_path
- normalized_path
- volume_identifier when available
- enabled
- created_at
- last_scanned_at

### `audio_files`

- id
- stable_file_id
- source_root_id
- current_relative_path
- basename
- normalized_basename
- extension
- size_bytes
- windows_created_at
- windows_modified_at
- first_discovered_at
- last_seen_at
- duration_seconds
- sha256
- readable
- zero_byte
- duplicate_group
- current_source_version_id
- current_state
- preferred_transcript_id
- created_at
- updated_at

### `audio_path_history`

- id
- audio_file_id
- source_root_id
- relative_path
- first_seen_at
- last_seen_at
- active

### `audio_source_versions`

- id
- audio_file_id
- size_bytes
- modified_at
- sha256
- discovered_at
- stale_at
- is_current

### `chat_exports`

- id
- source_root_id
- relative_path
- sha256
- inferred_chat_name
- parser_version
- first_discovered_at
- last_parsed_at
- duplicate_of_id
- parse_status
- warning_count

### `chat_voice_references`

- id
- chat_export_id
- line_number
- sender_original
- chat_original
- whatsapp_message_at
- referenced_filename
- normalized_filename
- parser_pattern
- parser_confidence
- warning
- header_hash

### `metadata_matches`

- id
- audio_file_id
- chat_voice_reference_id
- match_status
- confidence
- evidence_json
- selected
- created_at
- updated_at

### `manual_metadata_overrides`

- id
- audio_file_id
- sender
- chat
- whatsapp_message_at
- note
- created_at
- updated_at
- active

### `transcription_attempts`

- id
- audio_file_id
- source_version_id
- model_name
- model_hash
- engine_name
- engine_version
- language
- settings_json
- attempt_number
- state
- started_at
- completed_at
- processing_seconds
- detected_language
- language_probability
- raw_transcript
- normalized_transcript
- segment_json
- error_type
- safe_error_message
- technical_log_reference
- quality_status
- quality_score
- quality_reasons_json
- created_at

### `manual_transcripts`

- id
- audio_file_id
- based_on_attempt_id
- text
- verified
- note
- created_at
- updated_at
- active

### `processing_events`

- id
- audio_file_id nullable
- session_id
- event_type
- event_at
- safe_message
- details_json

### `worker_sessions`

- id
- instance_token
- pid
- started_at
- heartbeat_at
- requested_action
- state
- stopped_at

### `export_runs`

- id
- format
- options_json
- started_at
- completed_at
- record_count
- output_path
- output_sha256
- status
- error

### `backups`

- id
- created_at
- backup_path
- manifest_sha256
- database_integrity_result
- app_version
- status

### `settings`

- key
- value_json
- updated_at

## 11.2 Database rules

- Use foreign keys.
- Use migrations.
- Use parameterized queries.
- Use short transactions.
- Commit after every completed or failed item.
- Store full transcript in SQLite so deleted exports can be rebuilt without audio.
- Create indexes for status, sender, chat, timestamps, normalized basename, fingerprint, and full-text search.
- Use FTS5 for transcript search if available in the bundled SQLite; otherwise implement a documented fallback.

---

# 12. PROCESSING STATE MACHINE

States:

- `discovered`
- `metadata_pending`
- `metadata_matched`
- `metadata_ambiguous`
- `queued`
- `processing`
- `completed_small`
- `completed_medium`
- `completed_preferred`
- `flagged`
- `failed`
- `no_speech`
- `paused`
- `stale_source_changed`
- `missing_source`
- `invalid_output`
- `manually_excluded`
- `verified`

## Startup recovery

On startup:

1. Validate database.
2. Find stale worker leases.
3. Convert stale `processing` records back to `queued`.
4. Preserve their failed/interrupted attempt history.
5. Keep completed records completed.
6. Do not globally reset the queue.

---

# 13. NO-REPEAT GUARANTEE

Before starting a transcription, verify:

1. Source still exists.
2. Current SHA-256 matches current source version.
3. A successful compatible transcription exists.
4. Preferred transcript is not invalidated.
5. No explicit reprocess request exists.

If true:

- skip;
- do not create another attempt;
- record `skipped_complete` event.

## If TXT or MD output is missing

Rebuild it from SQLite.

Do not retranscribe.

## If the source changes

- create a new source version;
- preserve old transcript;
- mark old transcript stale for the new source;
- queue only the changed version after user confirmation or configured policy.

## If settings change

Changing nonessential output settings must not trigger retranscription.

Changing the default model affects pending files only.

Explicit reprocess is required for completed files.

---

# 14. QUALITY CONTROL

Quality categories:

- `Baik`
- `Cukup`
- `Perlu Diperiksa`
- `Tidak Ada Suara`
- `Gagal`
- `Metadata Tidak Jelas`
- `Sumber Berubah`

Flag reasons may include:

- empty transcript;
- no speech;
- decoding failure;
- corrupted file;
- repeated phrase loop;
- repeated token loop;
- mostly punctuation;
- suspicious generic hallucination;
- very long duration with implausibly little text;
- low language confidence;
- unexpected language;
- ambiguous sender;
- missing WhatsApp timestamp;
- source changed;
- output integrity failure.

Do not mark every short voice note as wrong. Short audio can legitimately contain one word.

---

# 15. EXPORT BLUEPRINT

The database remains authoritative. Exports are reproducible views.

## 15.1 Simple export choices in UI

The `Buat Hasil` dialog provides:

- Markdown untuk Second Brain
- Text biasa
- CSV untuk Excel
- JSONL untuk data

Default selected:

- Markdown
- Text

## 15.2 Markdown strategy

### Recommended default: one Markdown file per day

Path:

```text
Output/Markdown/Daily/YYYY/YYYY-MM/YYYY-MM-DD.md
```

Benefits:

- fewer files than one file per voice note;
- chronological context;
- manageable AI ingestion;
- easy second-brain organization.

### Optional: one Markdown file per voice note

Path:

```text
Output/Markdown/Individual/YYYY/YYYY-MM/YYYY-MM-DD/<stable-id>.md
```

### Markdown index

```text
Output/Markdown/INDEX.md
```

Include links grouped by year/month/day and basic counts.

### Markdown front matter for daily files

```yaml
---
type: whatsapp_voice_note_transcripts
date: 2026-07-14
record_count: 42
generated_at: 2026-07-15T10:00:00+07:00
app: Different Network Transcribe
app_version: 1.0.0
---
```

### Entry format

```markdown
## 20:31 — Daniel

- **Chat:** Grup Different Network
- **Timestamp WhatsApp:** 2026-07-14 20:31:00
- **File:** `PTT-20260714-WA0043.opus`
- **Model:** Small
- **Kualitas:** Baik
- **ID:** `dnt:...`

Besok kita lanjutkan pembahasan halaman utama.
```

Avoid copying every technical field into the default second-brain Markdown. Keep it concise.

Provide an optional `Sertakan metadata teknis lengkap` checkbox, off by default.

### Unknown-date Markdown

```text
Output/Markdown/Unknown-Date.md
```

Do not place unknown records under a guessed date.

## 15.3 Text export

### Daily TXT

```text
Output/Text/Daily/YYYY/YYYY-MM/YYYY-MM-DD.txt
```

### Combined TXT

```text
Output/Text/semua-transkrip.txt
```

Combined TXT is optional because it may become very large.

Entry:

```text
============================================================
Timestamp WhatsApp : 14/07/2026 20:31:00
Pengirim           : Daniel
Chat               : Grup Different Network
Nama File          : PTT-20260714-WA0043.opus
Model              : small
Kualitas           : Baik
============================================================

Besok kita lanjutkan pembahasan halaman utama.
```

## 15.4 CSV

```text
Output/CSV/semua-transkrip.csv
```

Use UTF-8 BOM for Excel.

Columns:

- stable_id
- whatsapp_timestamp
- sender
- chat
- audio_filename
- audio_relative_path
- windows_created_at
- windows_modified_at
- discovered_at
- duration_seconds
- metadata_match_status
- metadata_confidence
- preferred_model
- quality_status
- preferred_transcript
- attempt_count
- processing_started_at
- processing_completed_at
- latest_error

## 15.5 JSONL

```text
Output/JSONL/semua-transkrip.jsonl
```

One complete record per line.

## 15.6 Atomic export

- Write to a temporary file.
- Flush and close.
- Validate encoding and record count.
- Atomically replace final file.
- Preserve the last valid export if generation fails.

---

# 16. BACKUP AND COMPUTER MIGRATION

## 16.1 Normal backup

Create timestamped backups of:

- SQLite database;
- configuration;
- manual corrections;
- manifests;
- optional exports.

Do not duplicate all source audio by default.

## 16.2 Migration package

Extension:

`.dntbackup`

Example:

`DifferentNetworkTranscribe-Backup-2026-07-14.dntbackup`

Contents:

- database;
- settings;
- outputs if selected;
- reports;
- manual corrections;
- model manifest;
- source-root mappings;
- integrity manifest;
- app/schema version.

Optional checkboxes:

- Sertakan hasil ekspor
- Sertakan model
- Sertakan audio

Before including audio, calculate and display package size.

## 16.3 Restore

Workflow:

1. Install Different Network Transcribe.
2. Open application.
3. Click `Pulihkan Paket`.
4. Validate archive and manifest.
5. Back up any existing database.
6. Restore into a new staging location.
7. Run integrity checks.
8. Swap only after success.
9. Ask user to reconnect source folders if paths differ.
10. Relink by fingerprint.
11. Do not retranscribe matching completed audio.

---

# 17. GITHUB REPOSITORY AND RELEASE BLUEPRINT

## 17.1 Repository purpose

The repository contains:

- source code;
- tests;
- documentation;
- build scripts;
- installer script;
- GitHub Actions workflows;
- release notes;
- license notices.

It must not contain:

- private audio;
- private chat exports;
- private transcripts;
- real database;
- production logs;
- model weights in normal Git history;
- generated installer binaries committed into source history.

## 17.2 Suggested repository structure

```text
Different-Network-Transcribe/
├── app/
│   ├── ui/
│   ├── services/
│   ├── database/
│   ├── transcription/
│   ├── parsing/
│   ├── matching/
│   ├── exports/
│   ├── backup/
│   ├── models/
│   ├── resources/
│   └── main.py
├── worker/
│   └── main.py
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── ui/
│   └── fixtures/
├── installer/
│   └── different-network-transcribe.iss
├── packaging/
│   ├── pyinstaller/
│   └── model-manifest/
├── scripts/
│   ├── setup-dev.ps1
│   ├── test.ps1
│   ├── build.ps1
│   └── release.ps1
├── docs/
│   ├── USER_GUIDE_ID.md
│   ├── DEVELOPER_GUIDE.md
│   ├── ARCHITECTURE.md
│   ├── DATABASE.md
│   ├── RELEASE.md
│   └── PRIVACY.md
├── .github/
│   ├── workflows/
│   │   ├── ci.yml
│   │   ├── build-windows.yml
│   │   └── release.yml
│   ├── ISSUE_TEMPLATE/
│   └── pull_request_template.md
├── pyproject.toml
├── requirements-lock.txt
├── PROJECT_BLUEPRINT.md
├── README.md
├── CHANGELOG.md
├── SECURITY.md
├── LICENSE
└── THIRD_PARTY_NOTICES.md
```

## 17.3 GitHub downloads

Each tagged release must provide:

1. `DifferentNetworkTranscribe-Setup-x64.exe`
2. `DifferentNetworkTranscribe-Portable-x64.zip`
3. `DifferentNetworkTranscribe-Small-Offline-Setup-x64.exe` when under the release-asset size limit
4. `DifferentNetworkTranscribe-Model-Small.zip`
5. `DifferentNetworkTranscribe-Model-Medium.zip`
6. `SHA256SUMS.txt`
7. Release notes
8. Source code ZIP and TAR automatically generated by GitHub

Models must be release assets, not normal Git files.

GitHub currently enforces a 100 MiB single-object limit in normal repositories, while individual GitHub Release assets must remain under 2 GiB. The release workflow must check sizes before upload and fail with a clear message rather than publishing broken assets.

## 17.4 Release channels

- Stable: normal team use.
- Pre-release: internal testing.

Version format:

`vMAJOR.MINOR.PATCH`

## 17.5 GitHub Actions

### CI on pull requests

- install pinned dependencies;
- lint;
- type check;
- unit tests;
- integration tests using synthetic data;
- database migration tests;
- build smoke test.

### Windows build

- build one-folder app;
- verify no private data;
- build installer;
- build portable ZIP;
- run clean-location startup test;
- generate checksums;
- retain artifacts.

### Release on version tag

- run full CI;
- build assets;
- validate sizes;
- generate release draft;
- upload assets;
- never embed secrets or private test data;
- require manual approval before publishing stable release if practical.

---

# 18. INSTALLER BLUEPRINT

Use Inno Setup to create a conventional Windows installer.

## Installer behavior

- x64 only for v1.
- Per-user install by default.
- Install under `%LOCALAPPDATA%\Programs\Different Network Transcribe`.
- Add Start Menu shortcut.
- Optional Desktop shortcut.
- Register uninstaller.
- Preserve user data during upgrade.
- Uninstall asks separately whether to remove user data.
- No Python prerequisite.
- No terminal steps.
- No admin rights for normal installation.
- Display third-party notices.

## Standard versus offline installation

### Standard installer

Contains:

- application;
- Python runtime;
- PySide6/Qt;
- Faster-Whisper dependencies;
- PyAV;
- database migrations;
- resources.

The first-run wizard downloads Small or Medium.

### Small offline installer

Contains everything above plus Small model, if final asset stays under 2 GiB.

### Medium

Distribute as a separate verified model pack because app + Medium may approach or exceed practical release-asset size.

## SmartScreen

Code signing is recommended but not mandatory for internal v1. If no certificate exists, document that Windows SmartScreen may warn for a new unsigned installer.

---

# 19. SECURITY, PRIVACY, AND DATA HANDLING

- No analytics by default.
- No telemetry by default.
- No transcript upload.
- No cloud API.
- No external crash upload.
- No sensitive data in GitHub issues.
- Logs exclude full transcripts by default.
- Error dialog shows safe message, while local technical log stores stack trace.
- Never print entire exported chats.
- Sanitize logs before optional sharing.
- Backup files may contain private transcripts and must be clearly labeled.
- Use dependency pinning and checksum verification.
- Include third-party licenses.
- Use an LGPL-compatible FFmpeg/PyAV distribution path where applicable and preserve required notices.

---

# 20. ERROR HANDLING

One bad file must not stop the queue.

For each failure:

- mark attempt failed;
- save error type;
- save safe message;
- save technical log pointer;
- increment attempt count;
- continue.

Retry policy:

- normal run does not retry forever;
- default automatic retries: 1 for transient errors;
- manual retry available;
- user can reprocess selected files.

Example user message:

> File tidak dapat dibaca. File dilewati dan proses dilanjutkan.

Do not show raw tracebacks in the normal UI.

---

# 21. PAUSE, SAFE STOP, AND RESUME

## Pause

- stop assigning new files;
- finish current file or safe segment boundary;
- commit;
- remain ready to continue.

## Safe stop

- request shutdown;
- stop assigning new files;
- finish or release current record safely;
- commit database;
- remove worker lease;
- confirm saved progress.

## Closing while active

Dialog:

> Transkripsi masih berlangsung.

Buttons:

- Berhenti Aman dan Tutup
- Batalkan

Do not silently kill the worker.

## Crash recovery

- stale worker detected by heartbeat;
- interrupted attempt marked interrupted;
- only interrupted item requeued;
- completed files remain complete.

---

# 22. PERFORMANCE REQUIREMENTS

The application must handle at least 13,000 records without freezing.

Requirements:

- database pagination;
- lazy transcript loading;
- FTS query only when requested;
- one model instance;
- bounded queues;
- one transcription worker;
- no full transcript loading on startup;
- no export rebuild after every file;
- database indexes;
- short transactions;
- atomic writes;
- progress refresh no faster than needed.

ETA must use observed processing duration and total audio duration. Do not provide a misleading ETA after only one file.

---

# 23. TESTING BLUEPRINT

## 23.1 Unit tests

- Indonesian chat format.
- English chat format.
- bracketed timestamp.
- dot/colon time.
- 12/24 hour.
- two/four digit year.
- Unicode marks.
- multiline message.
- system message.
- sender containing punctuation/colon.
- duplicate exports.
- exact unique match.
- ambiguous match.
- unmatched audio.
- chat reference missing audio.
- fingerprint.
- changed-source detection.
- no-repeat logic.
- manual metadata override.
- manual transcript preservation.
- quality checks.
- Markdown formatting.
- TXT formatting.
- CSV UTF-8 BOM.
- JSONL validity.
- atomic export.
- migration manifest validation.

## 23.2 Database tests

- initial migration;
- upgrade migration;
- rollback after failed migration;
- WAL configuration;
- foreign keys;
- database integrity;
- backup/restore;
- 13,000 synthetic records;
- indexed paging;
- FTS;
- stale worker recovery;
- concurrent read while worker writes;
- duplicate worker prevention.

## 23.3 Worker tests

- model loading;
- model remains loaded;
- one valid audio;
- no speech;
- corrupted audio;
- cancellation;
- pause;
- safe stop;
- resume;
- processing failure continues queue;
- changed source during queue;
- completed file skipped.

## 23.4 UI tests

- first-run wizard;
- empty database;
- folder picker;
- scan;
- model choice;
- test run;
- start;
- pause;
- stop;
- table pagination;
- filters;
- edit transcript;
- manual metadata correction;
- exports;
- backup;
- restore;
- application close while active;
- Indonesian labels;
- understandable errors.

## 23.5 Packaging tests

- installer build;
- install to clean user folder;
- launch without system Python;
- uninstall;
- upgrade preserving data;
- portable ZIP launch;
- missing model flow;
- model download/import;
- release asset checksum;
- no private files packaged.

## 23.6 Limited real-data test

Maximum 20 files.

Select:

- very short;
- medium duration;
- longer;
- clear audio;
- noisy audio;
- different subfolders;
- matched metadata;
- unmatched metadata;
- duplicate basename if available.

Verify:

- transcription;
- sender;
- chat;
- WhatsApp time;
- Windows times;
- DB persistence;
- restart;
- no repeat;
- Markdown;
- TXT;
- source unchanged.

Do not run production.

---

# 24. IMPLEMENTATION PHASES FOR THE CODING AGENT

The agent must maintain:

`docs/IMPLEMENTATION_STATUS.md`

Each requirement must be marked:

- Not started
- In progress
- Implemented
- Tested
- Blocked

## Phase 0 — Safe inspection

- inspect repository;
- inspect folder structure;
- never print private content;
- count file extensions only if real input is available;
- identify available development tools;
- write risk report.

Deliverables:

- `docs/IMPLEMENTATION_PLAN.md`
- `docs/RISKS_AND_ASSUMPTIONS.md`
- `docs/IMPLEMENTATION_STATUS.md`

## Phase 1 — Project foundation

- Python environment;
- pyproject;
- locked dependencies;
- app entry point;
- logging;
- configuration;
- tests;
- CI skeleton.

Gate:

- application opens empty;
- tests run.

## Phase 2 — Database and migrations

- schema;
- repositories;
- indexes;
- WAL;
- integrity;
- migration tests.

Gate:

- 13,000 synthetic records;
- paging performance acceptable;
- migration and backup tests pass.

## Phase 3 — Discovery and fingerprinting

- source roots;
- scan;
- metadata;
- SHA-256;
- duplicate groups;
- path history;
- change detection.

Gate:

- repeated scan creates no duplicate records;
- moved fingerprint can relink;
- source files unchanged.

## Phase 4 — WhatsApp parser

- parser framework;
- multiple formats;
- diagnostics;
- duplicate export detection;
- tests.

Gate:

- all synthetic parser tests pass;
- unparsed headers reported safely.

## Phase 5 — Metadata matcher

- confidence;
- candidate storage;
- manual override;
- reports.

Gate:

- no sender guessing;
- ambiguous test stays ambiguous.

## Phase 6 — Transcription worker

- model manager;
- Small/Medium;
- worker process;
- pause/stop;
- attempt history;
- quality checks.

Gate:

- test audio succeeds;
- model loads once;
- crash recovery works;
- corrupted file does not stop queue.

## Phase 7 — No-repeat and recovery

- compatibility check;
- output regeneration;
- stale source;
- interrupted state;
- retry.

Gate:

- second run performs zero unnecessary transcription;
- deleted output regenerates from DB.

## Phase 8 — Exporters

- Markdown daily;
- Markdown individual optional;
- TXT;
- CSV;
- JSONL;
- index;
- atomic output.

Gate:

- counts match DB;
- UTF-8 verified;
- unknown-date separation works.

## Phase 9 — UI

- four sections;
- wizard;
- dashboard;
- table;
- details;
- review;
- settings;
- help.

Gate:

- responsive with 13,000 synthetic records;
- all normal tasks require no terminal.

## Phase 10 — Backup and migration

- backup;
- restore;
- `.dntbackup`;
- relink.

Gate:

- restore to a different path;
- no-repeat preserved.

## Phase 11 — Packaging

- PyInstaller one-folder;
- Inno Setup;
- portable ZIP;
- checksums;
- model pack.

Gate:

- clean-location smoke test;
- no system Python required.

## Phase 12 — GitHub workflows

- CI;
- build;
- release draft;
- asset size checks;
- checksum.

Gate:

- workflow configuration validated;
- artifacts named correctly.

## Phase 13 — Limited real test

- maximum 20;
- test report;
- no production.

## Phase 14 — Final audit

- audit every Definition of Done item;
- fix defects;
- final report;
- stop.

---

# 25. DEFINITION OF DONE

The project is not complete until all items below are evidenced.

## Application

- [ ] Application name is Different Network Transcribe.
- [ ] Indonesian UI.
- [ ] Four simple navigation sections.
- [ ] First-run wizard.
- [ ] Small/Medium choice.
- [ ] No manual Python installation.
- [ ] No terminal required.
- [ ] UI stays responsive.
- [ ] Separate worker.
- [ ] Duplicate workers blocked.

## Data

- [ ] Recursive audio scan.
- [ ] Recursive chat scan.
- [ ] Source files untouched.
- [ ] SHA-256 identity.
- [ ] Move/relink.
- [ ] SQLite state.
- [ ] Schema migrations.
- [ ] Backups.
- [ ] Restore.

## Metadata

- [ ] Sender parsed when evidence exists.
- [ ] Chat parsed.
- [ ] WhatsApp timestamp parsed.
- [ ] Windows creation time stored separately.
- [ ] Windows modification time stored separately.
- [ ] Unknown values not guessed.
- [ ] Manual override preserves original.

## Transcription

- [ ] Small works.
- [ ] Medium works.
- [ ] Model loaded once.
- [ ] Pause works.
- [ ] Safe stop works.
- [ ] Resume works.
- [ ] Failed file does not stop queue.
- [ ] Attempt history preserved.
- [ ] Completed files skipped.
- [ ] Changed files versioned.
- [ ] Deleted output regenerated without transcription.

## Output

- [ ] Daily Markdown.
- [ ] Optional individual Markdown.
- [ ] Markdown index.
- [ ] Daily TXT.
- [ ] Combined TXT.
- [ ] CSV UTF-8 BOM.
- [ ] JSONL.
- [ ] Unknown dates separated.
- [ ] Atomic export.
- [ ] DB/export record counts match.

## Distribution

- [ ] GitHub repository.
- [ ] README.
- [ ] User guide.
- [ ] Developer guide.
- [ ] Portable ZIP.
- [ ] Windows installer.
- [ ] Checksums.
- [ ] Model packs.
- [ ] Clean install test.
- [ ] Upgrade preserves data.
- [ ] Release workflow.
- [ ] No private data included.

## Scale

- [ ] 13,000 synthetic record UI test.
- [ ] Pagination.
- [ ] Search.
- [ ] Filters.
- [ ] Bounded memory.
- [ ] ETA based on observed data.

## Safety

- [ ] Local-only.
- [ ] No API.
- [ ] No telemetry by default.
- [ ] Logs avoid transcript bodies.
- [ ] No destructive source operation.
- [ ] Restore uses staging and validation.

---

# 26. REQUIRED DOCUMENTATION GENERATED BY THE AGENT

Create:

- `README.md`
- `docs/USER_GUIDE_ID.md`
- `docs/QUICK_START_ID.md`
- `docs/ARCHITECTURE.md`
- `docs/DATABASE.md`
- `docs/WHATSAPP_MATCHING_LIMITATIONS.md`
- `docs/SECOND_BRAIN_EXPORT.md`
- `docs/BACKUP_AND_MIGRATION.md`
- `docs/DEVELOPER_GUIDE.md`
- `docs/RELEASE.md`
- `docs/TROUBLESHOOTING_ID.md`
- `docs/PRIVACY.md`
- `THIRD_PARTY_NOTICES.md`
- `CHANGELOG.md`
- `SECURITY.md`

The user guide must not require understanding Python, pip, virtual environments, or terminals.

---

# 27. AGENT OPERATING RULES

The coding agent MUST:

- work in small verifiable phases;
- inspect before changing;
- preserve existing useful work;
- run tests;
- fix failures;
- avoid large blind rewrites;
- avoid reading 13,000 audio files into its context;
- use synthetic fixtures;
- use only up to 20 real files;
- keep private transcript text out of chat responses;
- report blockers honestly.

The coding agent MUST NOT:

- run all 13,000 production files;
- monitor production;
- upload data;
- use a cloud transcription API;
- invent sender metadata;
- claim perfection;
- skip installer testing;
- claim completion based only on code existing;
- delete source input;
- commit models to normal Git history.

---

# 28. STARTER PROMPT FOR CLAUDE CODE / CODEX / COPILOT

Copy this after placing this file in the repository root as `PROJECT_BLUEPRINT.md`:

```text
Read PROJECT_BLUEPRINT.md completely and treat it as the authoritative source of truth.

Build Different Network Transcribe in the implementation phases defined in the blueprint.

Before implementation:
1. inspect the repository safely;
2. create docs/IMPLEMENTATION_PLAN.md;
3. create docs/RISKS_AND_ASSUMPTIONS.md;
4. create docs/IMPLEMENTATION_STATUS.md with every Definition of Done item;
5. explain the chosen pinned dependency versions and packaging plan.

Then implement phase by phase. After every phase:
- run the required tests;
- update IMPLEMENTATION_STATUS.md;
- report evidence and remaining risks;
- do not continue past a failed quality gate without fixing it.

Critical boundaries:
- do not start the full 13,000-file transcription;
- use no more than 20 real files;
- do not upload private data;
- do not use cloud transcription APIs;
- do not require users to install Python or use a terminal;
- do not guess senders;
- do not alter source audio or chat exports;
- do not claim completion until the installer and portable ZIP have been smoke-tested.

The final runtime must work after this coding-agent session is closed.
```

---

# 29. CHECKPOINT AUDIT PROMPT

Use after every two or three phases:

```text
Audit the completed phases of Different Network Transcribe against PROJECT_BLUEPRINT.md.

Do not only inspect code. Run the relevant tests and reproduce the phase quality gates.

Check specifically:
- source files are read-only;
- SQLite is the source of truth;
- no-repeat logic is real, not based only on output file existence;
- interrupted state recovers safely;
- sender metadata is never guessed;
- all timestamp types remain separate;
- the model remains loaded in the worker;
- the UI does not perform transcription on its main thread;
- no private content is printed in logs or agent responses.

Fix all defects in the completed phases, update docs/IMPLEMENTATION_STATUS.md, and provide evidence. Do not start production transcription.
```

---

# 30. FINAL AUDIT PROMPT

```text
Perform the final release audit of Different Network Transcribe against every item in PROJECT_BLUEPRINT.md.

Run:
- all automated tests;
- database migration tests;
- 13,000 synthetic-record UI tests;
- no-repeat tests;
- crash/recovery tests;
- deleted-output regeneration tests;
- changed-source tests;
- backup/restore tests;
- cross-path migration and relinking tests;
- Markdown/TXT/CSV/JSONL export-integrity tests;
- worker-lock tests;
- installer build;
- portable ZIP build;
- clean-install smoke test;
- upgrade-preserves-data test;
- limited real test of no more than 20 files.

Verify GitHub release assets, naming, checksums, and size limits.

Fix all defects found.

Do not start the full 13,000-file transcription.

The final report must include:
1. application version;
2. automated test totals;
3. limited real-test results;
4. installer path and SHA-256;
5. portable ZIP path and SHA-256;
6. model-pack paths and SHA-256;
7. database location;
8. exact/ambiguous/unmatched metadata counts;
9. known limitations;
10. evidence that the app works without Python, terminal, coding agent, or cloud API;
11. exact next steps for the user.
```

---

# 31. USER ACCEPTANCE TEST

Before approving v1.0, the user or team should perform:

1. Install on the primary PC.
2. Select actual audio and chat folders.
3. Choose Small.
4. Scan.
5. Test 20.
6. Verify at least several sender/timestamp matches manually.
7. Start 50–100 files.
8. Pause.
9. Close and reopen.
10. Resume.
11. Confirm completed count is not repeated.
12. Delete one generated MD/TXT.
13. Regenerate output without audio transcription.
14. Retry one failed file.
15. Export daily Markdown.
16. Open Markdown in the chosen second-brain workflow.
17. Create backup.
18. Restore in a different folder.
19. Install on a second computer.
20. Relink source folder.
21. Confirm completed audio remains completed.
22. Only then begin the initial 13,000-file production run.

---

# 32. RESEARCH BASIS AND AUTHORITATIVE REFERENCES

The architecture decisions were grounded in the following primary sources, checked in July 2026:

1. Faster-Whisper repository and documentation  
   https://github.com/SYSTRAN/faster-whisper  
   Key points: CPU `int8`, PyAV audio decoding, official benchmark table, Python requirements, CUDA-oriented GPU documentation.

2. OpenAI Whisper model reference  
   https://github.com/openai/whisper  
   Key points: Small/Medium model tradeoffs and approximate memory/speed classes.

3. Qt for Python / PySide6 deployment documentation  
   https://doc.qt.io/qtforpython-6/deployment/  
   Key points: official PySide6 desktop deployment options.

4. Inno Setup official documentation  
   https://jrsoftware.org/ishelp/  
   Key points: Windows installer creation and x64 installation support.

5. GitHub repository large-file limits  
   https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits

6. GitHub Releases limits  
   https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases  
   Key points: release assets are limited to under 2 GiB each; source ZIP/TAR is automatically generated for tagged releases.

7. WhatsApp official chat export instructions  
   https://faq.whatsapp.com/1180414079177245  
   Key point: chats can be exported with or without media; exact sender matching still depends on the contents of the exported text.

8. FFmpeg legal information  
   https://ffmpeg.org/legal.html  
   Key point: preserve and review LGPL/GPL obligations for any bundled decoding components.

---

# 33. FINAL PRODUCT SUMMARY

Different Network Transcribe v1.0 is complete only when a team member can:

1. Download the EXE installer from GitHub Releases.
2. Install normally.
3. Open the application.
4. Select source folders.
5. Choose Small or Medium.
6. Scan.
7. Test.
8. Start local transcription.
9. Pause and resume.
10. Review uncertain records.
11. Export clean Markdown and TXT.
12. Add new files later without repeating old work.
13. Back up and move to another computer.
14. Use it without Python, terminal commands, cloud APIs, or an active coding agent.

The initial 13,000 files are a one-time bulk job. The permanent value of the application is its reliable incremental workflow for all future voice notes.
