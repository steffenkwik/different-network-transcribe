# Implementation Status

**App version:** 0.2.0
**Updated:** 2026-07-16 — v0.2.0 public release published
**Evidence convention:** `Tested` means an automated gate or explicitly recorded limited local test has passed. `Implemented` means the code/workflow exists but needs an external publication or CI action.

## Phase progress

| Phase | Deliverable | Status | Evidence |
|---|---|---|---|
| 0 | Safe inspection and mandatory design documents | Tested | Required docs, dependency imports, FTS5, privacy guard |
| 1 | Foundation, config, logs, entry point, layer rules | Tested | Unit/UI startup tests; privacy-safe JSONL logs |
| 2 | SQLite, WAL, migrations, FTS5, paging | Tested | 13,000 synthetic rows; initial page 0.010 s; offset page 0.012 s; migration `0005` adds persistent file-selection safety |
| 3 | Discovery, SHA-256 identity, relink | Tested | Synthetic idempotent scan, move/relink, changed-source tests |
| 4 | WhatsApp parser | Tested | Indonesian/English, time/year/BOM/RTL/multiline fixtures |
| 5 | Conservative metadata matching | Tested | Ambiguity stays unknown; threshold and override tests |
| 6 | Local worker and model registry | Tested | Lease, command, local model, failure isolation, heartbeat tests |
| 7 | No-repeat and recovery | Tested | Second synthetic session: zero inference/new attempts; explicit-only reprocess |
| 8 | Atomic exporters | Tested | Markdown/TXT/CSV/JSONL, deterministic rebuild, output regeneration |
| 9 | Indonesian PySide6 UI | Tested | Official DN logo, DN black/orange/chilli system, Academy typography, High model choice, multi-row safe history deletion, wizard, four sections, pagination, filters, review/detail/edit/playback |
| 10 | Backup, restore, diagnostic bundle | Tested | SQLite backup API, staging restore, manifest/audit and privacy tests |
| 11 | Windows packaging | Tested | Fresh installer + portable build and Python-free smoke test |
| 12 | CI/release workflows and privacy scan | Tested | GitHub Actions quality gate and Windows build-smoke passed for commit `44bd0f9` |
| 13 | Limited real-data test | Tested | User-confirmed 20-file run; all source SHA checks unchanged; second run skipped all |
| 14 | Final audit | Complete | `docs/FINAL_AUDIT.md` |

## Final local quality gate

```text
ruff check app worker tests scripts    PASS
mypy app worker                        PASS (46 source files)
pytest -m "not realdata"                PASS (143 tests)
private-data scan, staged source       PASS (current staged source)
private-data scan, release directory   PASS (3 release artifacts)
```

No real corpus run occurred during this final gate. All tests used synthetic fixtures except the already-recorded, user-selected 20-file Phase 13 test.

## Packaging evidence

```text
portable ZIP v0.2.0 SHA-256     4465A00848D234896A5F94188ADDFC8F1668C564D0C0F822FCA36AFFF9255104
installer v0.2.0 SHA-256        4020B13CCA12DE5F1667EBB820B18AEA68327E4CA0C3D7FD6C8E90BEF7919DAD
```

The refreshed clean smoke test passed the portable and installer launch paths:

```text
portable engine import exit      0
portable UI self-test exit       0; seven user-data folders created
installer UI self-test exit      0
post-uninstall application exe   absent
post-uninstall user database     preserved
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

- GitHub Actions quality-gate and Windows build-smoke passed for the post-audit UI refresh at commit `44bd0f9` (run `29497575364`). The public [v0.2.0 release](https://github.com/steffenkwik/different-network-transcribe/releases/tag/v0.2.0) now includes the smoke-tested installer, portable ZIP, and checksum manifest.
- Model packs are generated only by the explicit local `scripts/build_model_packs.py` command. Model weights stay ignored and are never included in the normal installer or Git history.
- The installer is unsigned. Windows SmartScreen warning remains an accepted, documented release risk.

## Post-audit UX refresh

- `docs/BRAND_GUIDELINES.md` is the visual source of truth: black-dominant surfaces, DN orange primary action, chilli red-orange controlled-attention action, and the official DN product mark.
- **Siapkan & Mulai Transkripsi** now opens a preflight dialog. It requires a locally installed Small/Medium choice, exposes a bounded file checklist, persists exclusions, and defaults to a batch of at most 20 files.
- Processing an entire incomplete collection remains possible only after a separate bulk opt-in and acknowledgement. A restart, re-scan, or settings change cannot silently re-enable excluded files.

## v0.2.0 DN identity and control update

- The app, installer, and desktop shortcut use the official DN Academy logo.
- The visual system uses DN black, primary orange `#FF4D00`, and chilli red-orange `#FF2D1A`; Archivo, JetBrains Mono, and Chakra Petch are bundled under their OFL licenses.
- High (`Systran/faster-whisper-large-v3`) is an explicit local option. It is never downloaded automatically and is clearly labelled as slower and RAM/disk intensive.
- **Hapus Riwayat Terpilih** requires Ctrl/Shift row selection and confirmation. It preserves audio, paths, source fingerprints, and chat metadata, and leaves cleared files disabled until selected again.
- The test runner now uses a fresh user-temp directory per run, avoiding stale Windows file locks.
- v0.2.0 portable/installer package smoke test passed with Python absent from `PATH`; both build assets contain the DN logo and bundled Academy fonts.
