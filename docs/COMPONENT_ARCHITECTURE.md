# Component Architecture — Different Network Transcribe

Implements `TECHNICAL_ADDENDUM.md` §1 (five layers) and §26 deliverable 1.
**This is the already-decided architecture made concrete. It is not a redesign.**

---

## 1. Final component diagram

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ PRESENTATION — app/ui/            (PySide6 only. No SQL. No regex.         │
│                                    No faster_whisper import.)              │
│                                                                            │
│  MainWindow ── Beranda │ Semua Transkrip │ Perlu Diperiksa │ Pengaturan    │
│  FirstRunWizard (8 steps)     DetailDrawer     ExportDialog                │
│  QAbstractTableModel (paged, lazy — never loads transcript bodies)         │
│  QTimer poll @ 750 ms ──────────────────────────────────┐                  │
└──────────────────────────┬──────────────────────────────┼──────────────────┘
                           │ calls use cases              │ reads status
                           v                              │
┌────────────────────────────────────────────────────────────────────────────┐
│ APPLICATION — app/services/       (orchestration, validation, commands)    │
│                                                                            │
│  ScanService          MatchingService      ExportService                   │
│  ModelSetupService    WorkerControlService BackupService                   │
│  ReviewService        SettingsService      IntegrityService                │
│  QueueService (decides what may be transcribed — NO-REPEAT lives here)     │
└──────────────────────────┬──────────────────────────────┬──────────────────┘
                           │                              │
                           v                              │
┌────────────────────────────────────────────────────────────────────────────┐
│ DOMAIN — app/models/              (pure Python. No I/O. No DB. Testable    │
│                                    without launching the UI.)              │
│                                                                            │
│  AudioFile  SourceVersion  ChatVoiceReference  MetadataMatch               │
│  TranscriptionAttempt  TranscriptVersion  ManualOverride                   │
│  ProcessingState (enum + legal transitions)                                │
│  CompatibilityKey   QualityVerdict   MatchConfidence   TimestampSet        │
└──────────────────────────┬──────────────────────────────┬──────────────────┘
                           │                              │
                           v                              v
┌────────────────────────────────────────────────────────────────────────────┐
│ INFRASTRUCTURE                                                             │
│                                                                            │
│  app/database/     Connection (WAL) · MigrationRunner · Repositories · FTS5│
│  app/parsing/      WhatsAppExportParser (versioned, pattern-ID tagged)     │
│  app/matching/     Matcher + confidence rules                              │
│  app/transcription/TranscriptionEngine (ABC) ← FasterWhisperEngine         │
│                    ModelRegistry · ModelInstaller · AudioDecoder (PyAV)     │
│                    QualityChecker                                          │
│  app/exports/      MarkdownExporter · TextExporter · CsvExporter ·         │
│                    JsonlExporter · AtomicWriter                            │
│  app/backup/       BackupService · DntBackupPackage · RestoreStaging       │
└──────────────────────────┬──────────────────────────────┬──────────────────┘
                           │                              │
                           v                              v
              ┌──────────────────────────┐    ┌──────────────────────────────┐
              │ SQLite (SOURCE OF TRUTH) │    │ Filesystem                   │
              │ WAL · FK ON · FTS5       │    │ Source audio  (READ-ONLY)    │
              │ different_network_       │    │ Chat exports  (READ-ONLY)    │
              │ transcribe.sqlite3       │    │ Output/ (derived, rebuildable)│
              └────────────┬─────────────┘    └──────────────────────────────┘
                           ^
                           │ single processing writer
┌──────────────────────────┴─────────────────────────────────────────────────┐
│ WORKER RUNTIME — worker/          (separate OS process. No UI widgets.)    │
│                                                                            │
│  WorkerLoop: lease → poll commands → claim next → decode → transcribe →    │
│              quality-check → commit → heartbeat(2 s) → status.json(1 s)    │
│  Model held LOADED for the whole session (loaded exactly once).            │
└────────────────────────────────────────────────────────────────────────────┘
```

## 2. Enforced dependency rules (checked by `tests/unit/test_architecture_layers.py`)

| Rule | Enforcement |
|---|---|
| UI contains no SQL, no parser regex, no engine call | AST scan of `app/ui/` for `sqlite3`, `faster_whisper`, `execute(` |
| Repositories never import PySide6 | Import scan of `app/database/`, `app/models/`, `app/parsing/`, `app/matching/`, `app/exports/`, `app/transcription/` |
| Worker never touches widgets | Import scan of `worker/` for `app.ui` / `PySide6` |
| Domain has no I/O | Import scan of `app/models/` for `sqlite3`, `os`, `pathlib.Path.open`, `requests` |
| No long op on UI thread | Transcription only reachable via the worker process; scanning/export run on `QThreadPool` |

A violation **fails the test suite**. This is how "UI must not contain business logic" stops being a slogan.

## 3. Threading model

| Work | Where it runs |
|---|---|
| Transcription | **Separate worker process.** Never in the UI process. |
| Scanning + SHA-256 hashing | `QRunnable` on `QThreadPool` in the UI process (I/O-bound, cancellable, progress-reporting) |
| Chat parsing + matching | `QThreadPool` |
| Export generation | `QThreadPool` |
| Backup / restore | `QThreadPool` |
| DB reads for the table view | UI thread, but **paged** (`LIMIT`/`OFFSET` with covering indexes) and never selecting transcript bodies |

Each thread and each process opens **its own SQLite connection** (addendum §3.6). Connections are never shared across threads or processes.

## 4. The no-repeat decision point (single chokepoint)

`QueueService.claimable_audio_ids()` is the **only** place that decides a file may be transcribed. Both the UI ("Mulai / Lanjutkan") and the worker go through it. It applies blueprint §13 in order:

```text
for each candidate audio_file:
    1. source path still exists?            no  → state = missing_source, SKIP
    2. on-disk SHA-256 == current_source_version.sha256?
                                            no  → new source version, state = stale_source_changed,
                                                  old transcript preserved, requeue only per policy
    3. completed successful attempt exists for THIS source_version?
                                            yes → 4
                                            no  → CLAIMABLE
    4. preferred transcript present and not invalidated?
                                            no  → CLAIMABLE
                                            yes → 5
    5. explicit reprocess request pending?  yes → CLAIMABLE (new attempt, old attempts preserved)
                                            no  → SKIP, emit `skipped_complete` processing_event
```

**Output files are never consulted.** A missing `.md`/`.txt` is regenerated from SQLite; it can never cause a retranscription. **Settings drift never requeues** — see `TRANSCRIPT_COMPATIBILITY_KEY.md` §4.

## 5. Failure domains (addendum §17) — isolated by design

| Domain | Blast radius | Guarantee |
|---|---|---|
| Scanner | one file row | Unreadable file ⇒ `readable=0`, scan continues |
| Parser | one chat export | Bad export ⇒ `parse_status='failed'`, **no transcription impact** |
| Matching | one audio row | Ambiguity ⇒ review queue, transcript untouched |
| Model setup | session | Missing model ⇒ worker exits cleanly, UI returns user to model setup |
| Audio decode | one attempt | Corrupt file ⇒ attempt `failed`, **queue continues** |
| Transcription | one attempt | Exception ⇒ attempt `failed` + safe message, queue continues |
| Database | app | `quick_check` at startup; corruption ⇒ read-only UI + restore prompt |
| Export | none | Export failure **never** invalidates a transcript; last valid export preserved |
| Backup | none | Failure leaves live DB untouched |

Parser improvements re-run parsing and re-run matching. They **never** touch `transcription_attempts`. The two pipelines are independent (addendum §9).

## 6. Timestamp discipline (blueprint §10, addendum §14)

Ten distinct fields, never conflated, never cross-assigned:

`whatsapp_message_at` · `windows_created_at` · `windows_modified_at` · `first_discovered_at` · `last_scanned_at` · `transcription_started_at` · `transcription_completed_at` · `last_attempt_at` · `last_exported_at` · `last_validated_at`

Stored as **ISO 8601 with timezone**. Displayed in local time. UI labels are exactly:
- `Timestamp WhatsApp` — from the chat export only. If absent: **"Timestamp WhatsApp tidak diketahui"**.
- `File dibuat di Windows`
- `File diubah di Windows`

The label `Tanggal File` is **forbidden**, and a unit test greps the i18n resource file to prove it is absent.

## 7. Export format contract (addendum §12, §13 — deliverable 6)

### Daily Markdown — `Output/Markdown/Daily/2026/2026-07/2026-07-14.md`

```markdown
---
type: whatsapp_voice_note_transcripts
date: 2026-07-14
record_count: 2
app: Different Network Transcribe
app_version: 1.0.0
---

<a id="dnt-a81f29c2"></a>
## 20:31 — Daniel

- **Chat:** Grup Different Network
- **Timestamp WhatsApp:** 2026-07-14 20:31:00
- **File:** `PTT-20260714-WA0043.opus`
- **Model:** Small
- **Kualitas:** Baik

Besok kita lanjutkan pembahasan halaman utama.

<a id="dnt-c4d0be71"></a>
## 20:44 — Pengirim tidak diketahui

- **Chat:** Grup Different Network
- **Timestamp WhatsApp:** 2026-07-14 20:44:00
- **File:** `PTT-20260714-WA0044.opus`
- **Model:** Small
- **Kualitas:** Perlu Diperiksa

Ini contoh transkrip kedua.
```

Rules:
- `generated_at` is **omitted by default** so second-brain files do not churn on every export. Enabling it is an explicit option.
- With `generated_at` omitted, the same DB state produces **byte-identical** output. Asserted by test.
- Ordering: valid WhatsApp timestamps chronologically; ties broken by stable ID; unknown-time records go to `Output/Markdown/Unknown-Date.md` and are **never** placed under a guessed date.
- SHA-256, engine settings, DB IDs, error history, and Windows timestamps are **excluded** unless `Sertakan metadata teknis lengkap` is checked.

### Individual Markdown filename (addendum §13)

```text
2026-07-14__PTT-20260714-WA0043__a81f29c2.md
<date-or-"unknown">__<windows-safe-basename>__<short-stable-id>.md
```

Windows-safe normalization handles reserved names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`…`LPT9`), trailing dots/spaces, invalid characters `<>:"/\|?*`, Unicode names, and long paths (`\\?\` prefix; generated paths kept short).

### Atomic write (blueprint §15.6)

`write temp → flush → fsync → validate encoding + record count → os.replace() → fsync dir`.
On failure the previous valid export survives untouched.

## 8. Process lifecycle

```text
UI start
  ├─ load config (TOML, validated, last-known-good fallback)
  ├─ PRAGMA quick_check
  ├─ run pending migrations (backup first)
  ├─ recover stale worker leases → interrupted `processing` rows → `queued`
  │    (completed rows stay completed; the queue is NEVER globally reset)
  └─ show MainWindow

User clicks "Mulai / Lanjutkan"
  ├─ WorkerControlService acquires lease (fails fast if a live lease exists →
  │    "Proses transkripsi sudah berjalan.")
  ├─ spawn worker process
  └─ poll status.json @750 ms + DB counts

User closes window while running
  └─ "Transkripsi masih berlangsung." → [Berhenti Aman dan Tutup] / [Batalkan]
     The worker is NEVER silently killed.
```
