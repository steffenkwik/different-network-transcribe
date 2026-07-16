# Implementation Status

**App version:** 0.1.0
**Updated:** 2026-07-16
**Evidence convention:** `Tested` means an automated gate or explicitly recorded limited local test has passed. `Implemented` means the code/workflow exists but needs an external publication or CI action.

## Phase progress

| Phase | Deliverable | Status | Evidence |
|---|---|---|---|
| 0 | Safe inspection and mandatory design documents | Tested | Required docs, dependency imports, FTS5, privacy guard |
| 1 | Foundation, config, logs, entry point, layer rules | Tested | Unit/UI startup tests; privacy-safe JSONL logs |
| 2 | SQLite, WAL, migrations, FTS5, paging | Tested | 13,000 synthetic rows; initial page 0.010 s; offset page 0.012 s |
| 3 | Discovery, SHA-256 identity, relink | Tested | Synthetic idempotent scan, move/relink, changed-source tests |
| 4 | WhatsApp parser | Tested | Indonesian/English, time/year/BOM/RTL/multiline fixtures |
| 5 | Conservative metadata matching | Tested | Ambiguity stays unknown; threshold and override tests |
| 6 | Local worker and model registry | Tested | Lease, command, local model, failure isolation, heartbeat tests |
| 7 | No-repeat and recovery | Tested | Second synthetic session: zero inference/new attempts; explicit-only reprocess |
| 8 | Atomic exporters | Tested | Markdown/TXT/CSV/JSONL, deterministic rebuild, output regeneration |
| 9 | Indonesian PySide6 UI | Tested | Wizard, four sections, pagination, filter, review/detail/edit/playback tests |
| 10 | Backup, restore, diagnostic bundle | Tested | SQLite backup API, staging restore, manifest/audit and privacy tests |
| 11 | Windows packaging | Tested | Fresh installer + portable build and Python-free smoke test |
| 12 | CI/release workflows and privacy scan | Tested | GitHub Actions quality gate and Windows build-smoke passed for commit `968cddc` |
| 13 | Limited real-data test | Tested | User-confirmed 20-file run; all source SHA checks unchanged; second run skipped all |
| 14 | Final audit | Complete | `docs/FINAL_AUDIT.md` |

## Final local quality gate

```text
ruff check app worker tests scripts    PASS
mypy app worker                        PASS (43 source files)
pytest -m "not realdata"                PASS (134 tests)
private-data scan, staged source       PASS (104 files)
private-data scan, release directory   PASS
```

No real corpus run occurred during this final gate. All tests used synthetic fixtures except the already-recorded, user-selected 20-file Phase 13 test.

## Packaging evidence

```text
portable ZIP SHA-256     5A56711700D7FBCB78CD272E7E0289DABEF969B42ADB74323AEFC5A4F39DC220
installer SHA-256        A6D952B8E28246C1711464FAAEC05E3D72F133B8B6CB0727048B8E80F14AD07B
```

The recorded clean smoke test passed both lanes:

```text
ENGINE_IMPORT_SELF_TEST PASS numpy=2.5.1 faster_whisper=1.1.1
SELF_TEST PASS visible=True title='Different Network Transcribe' platform='windows' version=0.1.0
PASS portable ZIP
PASS installer
```

The installer lane additionally installs into a fresh temporary directory, launches with Python removed from `PATH`, re-installs over the same application folder while checking user-data database bytes remain unchanged, uninstalls, and confirms that user data remains.

## Limited real-data evidence (strictly capped)

The recorded Phase 13 batch contained **20** user-selected audio files, never the full corpus. Aggregate-only verification:

```text
database integrity_check       ok
completed attempts             20
preferred completed records    20
source SHA-256 checks          20 checked; 0 mismatch
second worker session          0 new attempts; 20 skipped_complete events
derived formats                Markdown, TXT, CSV, JSONL present
```

## Distribution follow-up

- The public GitHub repository is current. GitHub Actions quality-gate and build-smoke both passed for commit `968cddc`.
- Model packs are generated only by the explicit local `scripts/build_model_packs.py` command. Model weights stay ignored and are never included in the normal installer or Git history.
- The installer is unsigned. Windows SmartScreen warning remains an accepted, documented release risk.
