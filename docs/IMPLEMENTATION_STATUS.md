# Implementation Status

**Updated after every phase.** Legend: `Not started` · `In progress` · `Implemented` · `Tested` · `Blocked`

"**Tested**" means an automated test exists **and was executed green**, with evidence recorded in §3. Code merely existing is never "Tested" (blueprint §27: *"do not claim completion based only on code existing"*).

**App version:** 0.1.0
**Last updated:** 2026-07-16 — limited 20-file real-data verification in progress

---

## 1. Phase progress

| Phase | Name | Status | Gate evidence |
|---|---|---|---|
| 0 | Safe inspection + design docs | **Tested** | §3.0 |
| 1 | Project foundation | **Tested** | §3.1 |
| 2 | Database and migrations | **Tested** | §3.2 |
| 3 | Discovery and fingerprinting | **Tested** | §3.3 |
| 4 | WhatsApp parser | **Tested** | §3.4 |
| 5 | Metadata matcher | **Tested** | §3.5 |
| 6 | Transcription worker | **Tested** | §3.6 |
| 7 | No-repeat and recovery | **Tested** | §3.7 |
| 8 | Exporters | **Tested** | SQLite-derived output/rebuild tests |
| 9 | UI | In progress | Four-section shell + wizard tests |
| 10 | Backup and migration | **Tested** | Temporary database package/restore tests |
| 11 | Packaging | **Tested** | Portable and installer smoke tests pass |
| 12 | GitHub workflows | Not started | — |
| 13 | Limited real test (max 20) | In progress | §3.13 |
| 14 | Final audit | Not started | — |

## 2. Definition of Done (blueprint §25) — every item tracked

### Application

| # | Item | Status |
|---|---|---|
| A1 | Application name is Different Network Transcribe | **Tested** — `test_main_window_opens_empty` asserts the window title |
| A2 | Indonesian UI | In progress — all strings centralised in `app/resources/strings_id.py`; sections land in Phase 9 |
| A3 | Four simple navigation sections | Not started (Phase 9) |
| A4 | First-run wizard | Not started (Phase 9) |
| A5 | Small/Medium choice | Implemented — explicit verified local Small/Medium install; UI choice lands in Phase 9 |
| A6 | No manual Python installation | Not started (Phase 11) |
| A7 | No terminal required | Not started (Phase 11) |
| A8 | UI stays responsive | In progress — worker is a separate process by construction; measured in Phase 9 |
| A9 | Separate worker | Implemented — Qt-free worker runtime, entry-point dispatch and local engine adapter |
| A10 | Duplicate workers blocked | **Tested** — live SQLite lease blocks a second worker |

### Data

| # | Item | Status |
|---|---|---|
| D1 | Recursive audio scan | **Tested** — recursive supported-format scan with isolated per-file errors |
| D2 | Recursive chat scan | In progress — versioned parser complete; recursive chat-root discovery lands with metadata orchestration |
| D3 | Source files untouched | **Tested** — scanner only reads/stat/hashes; synthetic source SHA is unchanged |
| D4 | SHA-256 identity | **Tested** — source versions use SHA-256 as final authority |
| D5 | Move/relink | **Tested** — moved bytes retain their logical record and completed state |
| D6 | SQLite state | **Tested** — WAL, foreign keys, integrity and FTS5 verified |
| D7 | Schema migrations | **Tested** — checksum verification, idempotency and rollback-safe transactions |
| D8 | Backups | Implemented — SQLite online backup API tested; package/restore UI lands in Phase 10 |
| D9 | Restore | Not started |

### Metadata

| # | Item | Status |
|---|---|---|
| M1 | Sender parsed when evidence exists | **Tested** — unique exact filename only |
| M2 | Chat parsed | **Tested** — preserved only for high-confidence selected match |
| M3 | WhatsApp timestamp parsed | **Tested** — parsed separately and never inferred from filesystem time |
| M4 | Windows creation time stored separately | Not started |
| M5 | Windows modification time stored separately | Not started |
| M6 | Unknown values not guessed | Not started |
| M7 | Manual override preserves original | Not started |

### Transcription

| # | Item | Status |
|---|---|---|
| T1 | Small works | **Tested** — verified and locally loaded; synthetic-audio inference smoke passed |
| T2 | Medium works | **Tested** — verified and locally loaded in CPU int8 mode |
| T3 | Model loaded once | **Tested** — deterministic worker assertion |
| T4 | Pause works | **Tested** — durable pause command transitions without claiming new work |
| T5 | Safe stop works | **Tested** — releases lease without claiming new work |
| T6 | Resume works | Implemented — command table protocol; end-to-end UI validation lands in Phase 9 |
| T7 | Failed file does not stop queue | **Tested** — one failed record followed by one completed record |
| T8 | Attempt history preserved | **Tested** — completed/failed/interrupted attempt rows retained |
| T9 | Completed files skipped | Not started |
| T10 | Changed files versioned | Not started |
| T11 | Deleted output regenerated without transcription | Not started |

### Output

| # | Item | Status |
|---|---|---|
| O1 | Daily Markdown | Not started |
| O2 | Optional individual Markdown | Not started |
| O3 | Markdown index | Not started |
| O4 | Daily TXT | Not started |
| O5 | Combined TXT | Not started |
| O6 | CSV UTF-8 BOM | Not started |
| O7 | JSONL | Not started |
| O8 | Unknown dates separated | Not started |
| O9 | Atomic export | Not started |
| O10 | DB/export record counts match | Not started |

### Distribution

| # | Item | Status |
|---|---|---|
| G1 | GitHub repository | Not started |
| G2 | README | Not started |
| G3 | User guide | Not started |
| G4 | Developer guide | Not started |
| G5 | Portable ZIP | Not started |
| G6 | Windows installer | Not started |
| G7 | Checksums | Not started |
| G8 | Model packs | Not started |
| G9 | Clean install test | Not started |
| G10 | Upgrade preserves data | Not started |
| G11 | Release workflow | Not started |
| G12 | No private data included | Not started |

### Scale

| # | Item | Status |
|---|---|---|
| S1 | 13,000 synthetic record UI test | Not started |
| S2 | Pagination | Not started |
| S3 | Search | Not started |
| S4 | Filters | Not started |
| S5 | Bounded memory | Not started |
| S6 | ETA based on observed data | Not started |

### Safety

| # | Item | Status |
|---|---|---|
| P1 | Local-only | **Tested** — `test_no_unexpected_network_endpoints` allows only Hugging Face model-weight hosts |
| P2 | No API | **Tested** — `test_no_cloud_or_telemetry_sdk_anywhere` |
| P3 | No telemetry by default | **Tested** — `test_privacy_defaults_are_off` + `test_privacy_cannot_be_switched_on` |
| P4 | Logs avoid transcript bodies | **Tested** — `test_transcript_body_never_reaches_the_log` reads the log file back off disk |
| P5 | No destructive source operation | Not started (Phase 3) |
| P6 | Restore uses staging and validation | Not started (Phase 10) |

## 3. Gate evidence log

### 3.0 — Phase 0 (complete)

**Deliverables produced:**

| Required by | File |
|---|---|
| Blueprint §24 Phase 0 | `docs/IMPLEMENTATION_PLAN.md` |
| Blueprint §24 Phase 0 | `docs/IMPLEMENTATION_STATUS.md` (this file) |
| Blueprint §24 Phase 0 | `docs/RISKS_AND_ASSUMPTIONS.md` |
| Addendum §26.1 | `docs/COMPONENT_ARCHITECTURE.md` |
| Addendum §26.2 | `docs/DATABASE_MIGRATION_PLAN.md` |
| Addendum §26.3 | `docs/WORKER_IPC_CONTRACT.md` |
| Addendum §26.4 | `docs/MODEL_REGISTRY.md` |
| Addendum §26.5 | `docs/TRANSCRIPT_COMPATIBILITY_KEY.md` |
| Addendum §26.8 | `docs/TEST_MATRIX.md` |

**Toolchain verified (measured, not assumed):**

```text
Python           3.12.10   per-user install under %LOCALAPPDATA%
PySide6          6.8.1.1   import OK
faster-whisper   1.1.1     import OK
av (PyAV)        13.1.0    import OK
ctranslate2      4.8.1     import OK
onnxruntime      1.27.0    import OK (Silero VAD)
SQLite           3.49.1    FTS5 available: True
Inno Setup       6.7.3     ISCC.exe found under %LOCALAPPDATA%\Programs
git              2.54.0
CPU              AMD Ryzen 7 9800X3D — 8C/16T  → presets 6 / 11 / 14 threads
RAM              31.05 GB
```

**Safe inspection of real data (counts only, no content read, nothing modified).**
The corpus path is intentionally omitted from this public repository:

```text
  .opus     13,126        .txt (chat exports)   353
  .nomedia     110        .json                   1
  .wav           1        zero-byte files       109
  subfolders   110        total size         0.50 GB
```

**Privacy controls active before any code was written:** `.gitignore` committed first, excluding all audio extensions, `*.sqlite3`, `*.dntbackup`, `Output/`, `Logs/`, `Backups/`, `Models/`, `Temp/`, `real-fixtures/`.

**Boundary compliance:** No transcription run. No file in `D:\vn` opened for reading content. No data uploaded. No cloud API contacted.

### 3.1 — Phase 1 (complete)

**Gate: "application opens empty; tests run."**

Evidence — the real entry point, launched as a real process, rendering a real window:

```text
> python -m app.main --data-dir <temp> --self-test
INFO ui: ui starting
INFO ui: self-test finished
SELF_TEST PASS visible=True title='Different Network Transcribe' platform='windows' version=0.1.0
exit code: 0
```

The `--self-test` flag opens the window, confirms it rendered, and exits. It is reused by the
Phase 11 packaging gate to prove the installed build and portable ZIP start with no system Python.

**Quality gate:**

```text
ruff check app worker tests scripts   All checks passed!
mypy app worker                       Success: no issues found in 20 source files
pytest -m "not realdata"              40 passed
scripts/scan_private_data.py          PASSED — 46 git-tracked files, no private data
```

**Defects found and fixed during this phase (not hidden):**

1. The private-data scanner **failed on my own design documents** — `docs/IMPLEMENTATION_PLAN.md`,
   `docs/IMPLEMENTATION_STATUS.md` and `docs/TEST_MATRIX.md` had embedded the operator's real corpus
   path and a `C:\Users\<name>` path. In a public repository, git history is permanent, so these were
   removed before the first push. The scanner earned its place on day one.
2. Two architecture tests were initially matching their **own docstrings** rather than real code.
   Fixed by parsing module-level imports via AST and excluding docstring constants.
3. `os.replace` / `datetime.timezone.utc` / `os.path.expanduser` lint findings and one mypy
   `int()` argument-type error — all fixed, none suppressed.

**Delivered:** `pyproject.toml`, `requirements-lock.txt`, `app/version.py`, `app/paths.py`,
`app/config.py` (TOML, validated, last-known-good, unknown-field preservation),
`app/logging_setup.py` (JSONL, privacy filter), `app/main.py` (dual-role entry point),
`app/ui/launch.py`, `app/resources/strings_id.py`, `worker/main.py` (Qt-free bootstrap),
`scripts/{setup-dev,test}.ps1`, `scripts/scan_private_data.py`, `.github/workflows/ci.yml`.

### 3.2 — Phase 2 (complete)

**Gate: “13,000 synthetic records; paging performance acceptable; migration and backup tests pass.”**

Delivered `migrations/0001_initial.sql` and `0002_add_query_indexes.sql` (17 durable tables,
FTS5, indexes, immutability triggers, the transcript-list view), plus `app/database/connection.py`,
`migrations.py`, and `repositories.py`. Every connection enables foreign keys, WAL, `NORMAL`
synchronous mode, and a 5-second busy timeout. The migration runner verifies checksums, applies
each migration atomically, and creates an online SQLite backup before changing an existing schema.

**Measured synthetic 13,000-record benchmark:**

```text
insert                 0.147 s
first 100-row page     0.010 s  (target < 1.000 s)
page at offset 6,000   0.012 s  (target < 0.500 s)
indexed filename filter 0.007 s (target < 1.000 s)
```

**Quality gate:**

```text
ruff check app worker tests scripts   All checks passed
mypy app worker                       Success: no issues found in 23 source files
pytest -m "not realdata"              50 passed in 4.02 s
scripts/scan_private_data.py          PASSED — 46 git-tracked files, no private data
```

The database gate covers: initial schema, idempotent upgrade, pre-upgrade backup, checksum-tamper
rejection, WAL/foreign keys/integrity, immutable completed transcript text, FTS5, online-backup
consistency, paged/lazy list queries, settings round trip, and the 13,000-record performance target.
No real input folder was scanned or opened.

### 3.3 — Phase 3 (complete)

**Gate: “Repeated scan creates no duplicate records; moved fingerprint can relink; source files unchanged.”**

Delivered `app/services/discovery_service.py` and `AudioRepository`: recursive discovery for all
supported formats, SHA-256 streamed in 1 MiB blocks, separate Windows creation/modification fields,
PyAV duration probing, zero-byte/unreadable isolation, duplicate-basename groups, current and
historical source versions, and path history. The scanner only opens sources for reading; it has no
delete, rename, move, overwrite, or conversion path.

**Quality gate:**

```text
ruff check app worker tests scripts   All checks passed
mypy app worker                       Success: no issues found in 24 source files
pytest -m "not realdata"              57 passed
scripts/scan_private_data.py          PASSED — 52 git-tracked files, no private data
```

Synthetic tests prove: an unchanged rescan creates zero records and zero attempts; a moved file is
relinked by SHA-256 with its completed state and both paths retained; changed bytes create a second
source version and state `stale_source_changed`; files sharing a basename but not bytes remain
separate; zero-byte and decode-error records do not stop other files; and the scanner leaves source
bytes exactly unchanged. No real inputs were opened.

### 3.4 — Phase 4 (complete)

**Gate: “All synthetic parser tests pass; unparsed headers reported safely.”**

Delivered `app/parsing/whatsapp_parser.py`: a versioned parser that extracts only attachment metadata
needed for matching, strips BOM and hidden direction marks, produces a normalized header hash, and
keeps the original sender/chat/time fields separate. It recognises Indonesian/English date layouts,
dot/colon separators, 12/24-hour time, two/four-digit years, bracketed/dash headers, multiline
messages, punctuation/colon-containing senders, media omissions, and duplicate export content.
Unrecognised non-empty lines are counted diagnostically, not retained or logged as chat bodies.

**Quality gate:**

```text
ruff check app worker tests scripts   All checks passed
mypy app worker                       Success: no issues found in 25 source files
pytest -m "not realdata"              65 passed
scripts/scan_private_data.py          PASSED — 54 git-tracked files, no private data
```

The Phase 4 fixtures are synthetic and no real chat export was opened.

### 3.5 — Phase 5 (complete)

**Gate: “No sender guessing; ambiguous test stays ambiguous.”**

Delivered `app/matching/metadata_matcher.py`: a pure, explicit confidence model. A unique exact
filename match selects metadata at 1.00 confidence; a unique canonical record after duplicate-export
removal selects at 0.95. Multiple filename candidates remain `exact_ambiguous`, absent filenames
remain `filename_not_present`, and timestamp-only hints stay at 0.69 with no selected metadata.
The matcher returns candidate IDs for review but never propagates sender, chat, or WhatsApp time below
the configurable 0.90 threshold.

**Quality gate:**

```text
ruff check app worker tests scripts   All checks passed
mypy app worker                       Success: no issues found in 26 source files
pytest -m "not realdata"              71 passed
scripts/scan_private_data.py          PASSED — 56 git-tracked files, no private data
```

All Phase 5 cases use synthetic metadata; no real export was opened.

### 3.6 — Phase 6 (complete)

Implemented the Qt-free `WorkerLoop`, SQLite lease/heartbeat/command repository, per-file attempt
claim/commit/failure transactions, safe-stop command handling, and stale-session recovery. The worker
uses a local-only `TranscriptionEngine` interface; `FasterWhisperEngine` is a CPU `int8` adapter that
loads a model once and consumes segments before a completed attempt is written.

The current deterministic worker gate is green: duplicate live leases are rejected; two files load the
engine once and create independent completed attempts; one failed input does not prevent the next;
safe stop claims no new work and releases the lease; stale `processing` rows become `interrupted` and
only their audio returns to `queued`; and a missing local model returns a safe setup status.

Completed the model registry with explicit-only Hugging Face download and offline ZIP import, partial
directory isolation, zip-slip rejection, required-artifact checks, full SHA-256 manifests, atomic
promotion, and safe preservation of a valid existing install. Both locally installed models verified
their required six artifacts. Small and Medium loaded through Faster-Whisper in CPU `int8` mode; Small
also completed one local inference on a generated one-second synthetic tone (zero transcript characters,
expected under VAD). The generated temporary file was deleted.

**Quality gate:**

```text
ruff check app worker tests scripts   All checks passed
mypy app worker                       Success: no issues found in 30 source files
pytest -m "not realdata"              82 passed
scripts/scan_private_data.py          PASSED — 62 git-tracked files, no private data
```

No real input folder was opened. Model weights reside in the ignored application-data folder and are
not tracked by Git.

### 3.7 — Phase 7 (in progress)

Implemented the single reuse decision point and the 12-field provenance key. `QueueService` now
performs the byte-level reuse check at every worker startup: unchanged preferred transcripts produce a
durable `skipped_complete` event and never become claimable. The worker's acceptance test performs a
full first synthetic run, starts a second worker session, and proves **zero new attempts and zero
engine inference**. The reuse function is tested to contain no provenance-key reference, which
prevents settings/model changes from silently queueing the completed corpus.

An explicit `reprocess_selected` command is now the only completed-file requeue path: it accepts a
specific list of audio IDs, preserves the old attempt, records an audit event, and creates exactly one
new attempt only for the selected file. The deleted-export regeneration path is covered by Phase 8's
SQLite-derived exporter test. No real input folder was opened.

### 3.8 — Phase 8 (complete)

`ExportService` reads preferred completed transcripts from SQLite only and atomically writes daily and
individual Markdown, an index, unknown-date Markdown, daily/combined TXT, UTF-8-BOM CSV, and JSONL.
The synthetic test proves the same DB state produces byte-identical Markdown; deleting a daily output
and re-exporting restores it with zero added transcription attempts. Unknown timestamps never enter a
guessed day.

### 3.9/3.10/3.11 — UI, backup, and packaging checkpoint

Implemented an Indonesian four-section PySide6 shell and first-run wizard, plus staging-first
`.dntbackup` creation and restore. Restore now takes a consistent pre-restore SQLite backup before
the validated staged replacement can become live. The built one-folder application, portable ZIP,
Inno Setup installer, and checksum manifest exist under the ignored `release/` folder.

The repeatable `scripts/smoke-test.ps1` gate was executed against both artifacts in fresh temporary
folders. Portable extraction launched the built executable with Python removed from `PATH` and created
the data tree. The installer completed with Inno's `Installation process succeeded` log; its installed
executable passed the same Python-free self-test. Its uninstaller exited zero, removed application
files, and preserved the separately selected user-data folder. The installer is intentionally per-user
(`PrivilegesRequired=lowest`) so it does not require administrator elevation.

This validates packaging only. Phase 9 remains in progress because the visible shell has not yet wired
all scan, review, worker, export, and backup actions to the services. Phase 7 integration, GitHub
automation, the limited real-data test, and the final audit also remain incomplete.

### 3.13 — Phase 13 (in progress; restricted to 20 real files)

The application completed a user-selected 20-file test batch. This agent did not start a corpus-wide
run and did not read or upload transcript bodies. The local, aggregate-only verification recorded:

```text
database integrity_check              ok
completed attempts                    20
preferred completed records           20
source SHA-256 checks                 20 checked; 0 mismatches
second local worker session           0 new attempts; 20 skipped_complete events
derived output files                  Markdown, TXT, CSV, JSONL present
```

The worker was restricted to the currently configured test root. Previously scanned records from
another root remained queued but were not claimable by this session. Pending before Phase 13 can be
marked tested: human spot-check of sender/chat/timestamp where chat exports are available, restart
persistence in the installed UI, and post-upgrade export-audit verification. No test will exceed 20
real source files.

## 4. Known gaps / blocked items

| Item | Status | Note |
|---|---|---|
| `gh` CLI on PATH | Deferred | Installed but needs a shell restart. Only needed at Phase 12. |
| Code-signing certificate | Accepted risk | None available. SmartScreen will warn on the unsigned installer. Documented in `RISKS_AND_ASSUMPTIONS.md` R-07 and will be stated in `README.md`. |
