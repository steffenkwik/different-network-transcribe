# Implementation Status

**Updated after every phase.** Legend: `Not started` · `In progress` · `Implemented` · `Tested` · `Blocked`

"**Tested**" means an automated test exists **and was executed green**, with evidence recorded in §3. Code merely existing is never "Tested" (blueprint §27: *"do not claim completion based only on code existing"*).

**App version:** 0.0.0 (pre-Phase-1)
**Last updated:** 2026-07-14 — end of Phase 0

---

## 1. Phase progress

| Phase | Name | Status | Gate evidence |
|---|---|---|---|
| 0 | Safe inspection + design docs | **Tested** | §3.0 |
| 1 | Project foundation | Not started | — |
| 2 | Database and migrations | Not started | — |
| 3 | Discovery and fingerprinting | Not started | — |
| 4 | WhatsApp parser | Not started | — |
| 5 | Metadata matcher | Not started | — |
| 6 | Transcription worker | Not started | — |
| 7 | No-repeat and recovery | Not started | — |
| 8 | Exporters | Not started | — |
| 9 | UI | Not started | — |
| 10 | Backup and migration | Not started | — |
| 11 | Packaging | Not started | — |
| 12 | GitHub workflows | Not started | — |
| 13 | Limited real test (max 20) | Not started | — |
| 14 | Final audit | Not started | — |

## 2. Definition of Done (blueprint §25) — every item tracked

### Application

| # | Item | Status |
|---|---|---|
| A1 | Application name is Different Network Transcribe | Not started |
| A2 | Indonesian UI | Not started |
| A3 | Four simple navigation sections | Not started |
| A4 | First-run wizard | Not started |
| A5 | Small/Medium choice | Not started |
| A6 | No manual Python installation | Not started |
| A7 | No terminal required | Not started |
| A8 | UI stays responsive | Not started |
| A9 | Separate worker | Not started |
| A10 | Duplicate workers blocked | Not started |

### Data

| # | Item | Status |
|---|---|---|
| D1 | Recursive audio scan | Not started |
| D2 | Recursive chat scan | Not started |
| D3 | Source files untouched | Not started |
| D4 | SHA-256 identity | Not started |
| D5 | Move/relink | Not started |
| D6 | SQLite state | Not started |
| D7 | Schema migrations | Not started |
| D8 | Backups | Not started |
| D9 | Restore | Not started |

### Metadata

| # | Item | Status |
|---|---|---|
| M1 | Sender parsed when evidence exists | Not started |
| M2 | Chat parsed | Not started |
| M3 | WhatsApp timestamp parsed | Not started |
| M4 | Windows creation time stored separately | Not started |
| M5 | Windows modification time stored separately | Not started |
| M6 | Unknown values not guessed | Not started |
| M7 | Manual override preserves original | Not started |

### Transcription

| # | Item | Status |
|---|---|---|
| T1 | Small works | Not started |
| T2 | Medium works | Not started |
| T3 | Model loaded once | Not started |
| T4 | Pause works | Not started |
| T5 | Safe stop works | Not started |
| T6 | Resume works | Not started |
| T7 | Failed file does not stop queue | Not started |
| T8 | Attempt history preserved | Not started |
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
| P1 | Local-only | Not started |
| P2 | No API | Not started |
| P3 | No telemetry by default | Not started |
| P4 | Logs avoid transcript bodies | Not started |
| P5 | No destructive source operation | Not started |
| P6 | Restore uses staging and validation | Not started |

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
Python           3.12.10   C:\Users\danie\AppData\Local\Programs\Python\Python312\python.exe
PySide6          6.8.1.1   import OK
faster-whisper   1.1.1     import OK
av (PyAV)        13.1.0    import OK
ctranslate2      4.8.1     import OK
onnxruntime      1.27.0    import OK (Silero VAD)
SQLite           3.49.1    FTS5 available: True
Inno Setup       6.7.3     C:\Users\danie\AppData\Local\Programs\Inno Setup 6\ISCC.exe
git              2.54.0
CPU              AMD Ryzen 7 9800X3D — 8C/16T  → presets 6 / 11 / 14 threads
RAM              31.05 GB
```

**Safe inspection of real data (counts only, no content read, nothing modified):**

```text
D:\vn\WhatsApp Voice Notes
  .opus     13,126        .txt (chat exports)   353
  .nomedia     110        .json                   1
  .wav           1        zero-byte files       109
  subfolders   110        total size         0.50 GB
```

**Privacy controls active before any code was written:** `.gitignore` committed first, excluding all audio extensions, `*.sqlite3`, `*.dntbackup`, `Output/`, `Logs/`, `Backups/`, `Models/`, `Temp/`, `real-fixtures/`.

**Boundary compliance:** No transcription run. No file in `D:\vn` opened for reading content. No data uploaded. No cloud API contacted.

## 4. Known gaps / blocked items

| Item | Status | Note |
|---|---|---|
| `gh` CLI on PATH | Deferred | Installed but needs a shell restart. Only needed at Phase 12. |
| Code-signing certificate | Accepted risk | None available. SmartScreen will warn on the unsigned installer. Documented in `RISKS_AND_ASSUMPTIONS.md` R-07 and will be stated in `README.md`. |
