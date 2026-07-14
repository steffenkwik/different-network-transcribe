# Implementation Plan — Different Network Transcribe v1.0

**Authority:** `PROJECT_BLUEPRINT.md` (product spec) + `TECHNICAL_ADDENDUM.md` (mandatory clarifications).
**This document does not redesign the architecture.** It makes the already-decided architecture executable.

---

## 1. Confirmed environment (measured, not assumed)

| Item | Value | Source |
|---|---|---|
| OS | Windows 11 Pro 10.0.26200, x64 | measured |
| CPU | AMD Ryzen 7 9800X3D — 8 cores / 16 logical | measured |
| RAM | 31.05 GB | measured |
| Free disk | C: 199 GB · D: 141 GB · E: 181 GB | measured |
| Python (build/runtime) | 3.12.10 at `%LOCALAPPDATA%\Programs\Python\Python312` | installed this session |
| Inno Setup | 6.7.3 — `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` | installed this session |
| git | 2.54.0 | measured |
| GitHub CLI | installed, needs shell restart to resolve on PATH | installed this session |
| Bundled SQLite | 3.49.1, **FTS5 available** | measured |

**CPU preset resolution on this machine** (blueprint §7.2 — never hardcoded, always derived from `os.cpu_count()`):

| Preset | Fraction | Threads on 16 logical |
|---|---|---|
| Rendah | ~40% | 6 |
| Seimbang | ~65–75% | 11 |
| Maksimal | ~85–90% | 14 |

## 2. Real data profile (read-only scan, counts only — no content read)

Source: `D:\vn\WhatsApp Voice Notes`

| Item | Count |
|---|---|
| `.opus` audio | 13,126 |
| `.txt` chat exports | 353 |
| `.nomedia` | 110 |
| `.json` | 1 |
| `.wav` | 1 |
| Zero-byte files | 109 |
| Subfolders | 110 |
| Total size | 0.50 GB |

This confirms the ~13,000-file scale in the blueprint. **This folder is read-only for the application and for this agent.** At most 20 files are used, for Phase 13 only.

## 3. Pinned dependency stack (resolved, not guessed)

Full lock: `requirements-lock.txt` (generated from a clean venv).

| Package | Version | Why this pin |
|---|---|---|
| Python | 3.12.10 | Blueprint mandates 3.12.x. Python 3.14 was present on this machine but has no reliable wheels for CTranslate2/PySide6 — rejected. |
| PySide6 | 6.8.1.1 | Official Qt binding; LTS-track 6.8; has Windows x64 wheels for 3.12. |
| faster-whisper | 1.1.1 | Blueprint engine. CPU `int8` supported. |
| ctranslate2 | 4.8.1 | Inference runtime behind faster-whisper. Satisfies `>=4.0,<5`. |
| av (PyAV) | 13.1.0 | Audio decoding without a separately installed FFmpeg. LGPL notices preserved in `THIRD_PARTY_NOTICES.md`. |
| onnxruntime | 1.27.0 | Required by faster-whisper's Silero VAD (`vad_filter = true`). |
| huggingface_hub | 0.26.5 | Model **weight** download only. Not an inference API. No audio ever leaves the machine. |
| tomlkit | 0.13.2 | TOML config with comment/unknown-field preservation (addendum §15.4). |
| platformdirs | 4.3.6 | Correct Windows user-data paths. |
| pytest / pytest-qt / pytest-cov | 8.3.4 / 4.4.0 / 6.0.0 | Unit, DB, worker, UI tests. |
| ruff / mypy | 0.8.6 / 1.14.1 | Lint + type gate in CI. |
| pyinstaller | 6.11.1 | One-folder packaging (blueprint §1). |
| Inno Setup | 6.7.3 | Windows installer. |

**Rejected:** any cloud transcription API, any telemetry SDK, any crash-reporting uploader. Blueprint §19.

## 4. Packaging plan

- **PyInstaller one-folder** (`--onedir`), not one-file. One-file unpacks a ~1 GB tree to `%TEMP%` on every launch; one-folder is what the blueprint specifies and is predictable with native DLLs (CTranslate2, Qt, PyAV).
- **Single executable, two roles.** The UI and the worker ship as one `DifferentNetworkTranscribe.exe`. The worker is launched as `sys.executable --worker --data-dir <path> --session <token>`. Rationale: a second PyInstaller entry point would duplicate the entire Qt/CTranslate2 payload. In dev, the same code path launches `python -m worker.main`. This is defined precisely in `WORKER_IPC_CONTRACT.md` §3.
- **Models are never bundled into the repo or the standard installer.** They are GitHub Release assets and/or downloaded on first run (blueprint §17.3, addendum §6.8).
- Artifacts per release: `DifferentNetworkTranscribe-Setup-x64.exe`, `DifferentNetworkTranscribe-Portable-x64.zip`, `DifferentNetworkTranscribe-Model-Small.zip`, `DifferentNetworkTranscribe-Model-Medium.zip`, `SHA256SUMS.txt`.

## 5. Repository layout (per blueprint §17.2)

```text
app/
  main.py            entry point; --worker flag dispatches to worker runtime
  models/            DOMAIN layer: entities, state machine, value objects (no I/O)
  services/          APPLICATION layer: use cases, orchestration, validation
  database/          INFRASTRUCTURE: connection, migrations runner, repositories
  transcription/     engine interface + faster-whisper adapter + model registry
  parsing/           WhatsApp export parser (versioned)
  matching/          metadata matcher + confidence rules
  exports/           markdown / txt / csv / jsonl writers + atomic write
  backup/            backup, .dntbackup package, restore with staging
  ui/                PySide6 widgets ONLY (no SQL, no regex, no engine calls)
  resources/         icons, i18n strings (Indonesian)
worker/
  main.py            worker runtime loop
migrations/          0001_initial.sql, 0002_*.sql ...
tests/
  unit/ integration/ ui/ fixtures/synthetic/
installer/           different-network-transcribe.iss
packaging/           pyinstaller spec, model-manifest
scripts/             setup-dev.ps1, test.ps1, build.ps1, release.ps1
docs/
.github/workflows/   ci.yml, build-windows.yml, release.yml
```

**Layer rule enforcement is a test, not a convention.** `tests/unit/test_architecture_layers.py` fails the build if:
- anything under `app/database/`, `app/transcription/`, `app/parsing/`, `app/matching/`, `app/exports/`, `app/models/` imports `PySide6`;
- anything under `app/ui/` contains raw SQL or imports `faster_whisper`;
- `worker/` imports `app.ui`.

## 6. Phase sequence and quality gates

Every phase ends with: run its tests → update `IMPLEMENTATION_STATUS.md` → show evidence → fix failures before continuing.

| Phase | Deliverable | Quality gate (must produce evidence) |
|---|---|---|
| **0** | Inspection, toolchain, 8 design docs, risks | Docs exist; venv imports faster-whisper + PySide6; no private data readable in repo |
| **1** | Config (TOML), logging, entry point, layer test, CI skeleton | App opens an empty window; `pytest` green; ruff+mypy clean |
| **2** | Schema, migrations, repositories, indexes, WAL, FTS5 | 13,000 synthetic records inserted; first page < 1 s; paged query < 500 ms; migration up/rollback tests pass |
| **3** | Scanner, SHA-256 identity, source versions, path history | Re-scan with no changes ⇒ **0 new audio rows, 0 new jobs**; moved file relinks by fingerprint; source mtime/size byte-identical before and after |
| **4** | WhatsApp parser (versioned, pattern IDs) | All synthetic format tests pass (ID/EN, dot/colon, 12/24h, 2/4-digit year, BOM, RTL marks, multiline, system msg, colon-in-name) |
| **5** | Matcher + confidence + manual override | Ambiguous stays ambiguous; confidence < 0.90 ⇒ sender **unknown**, never guessed; timestamp alone never yields high confidence |
| **6** | Model registry, download+verify, worker process, pause/stop, quality checks | Real audio transcribes; model loads **once** per session (asserted by counter); corrupted file does not stop queue; stale-lease recovery works |
| **7** | No-repeat + recovery | Addendum §23 scenario automated: second run ⇒ **zero new attempts, zero inference**; deleted MD/TXT regenerate from SQLite with no attempt added |
| **8** | Exporters + atomic write + index | DB count == export count; UTF-8 BOM on CSV; JSONL valid; unknown-date isolated; byte-identical re-export when `generated_at` omitted |
| **9** | UI: wizard + 4 sections | Responsive with 13,000 synthetic rows; no terminal needed for any normal task; Indonesian labels |
| **10** | Backup, `.dntbackup`, restore with staging | Restore to a *different* path; relink by fingerprint; no-repeat preserved |
| **11** | PyInstaller + Inno Setup + portable ZIP | Clean-location smoke test; launches with **no system Python**; upgrade preserves data |
| **12** | CI/build/release workflows + private-data scanner | Scanner passes on clean checkout; asset size checks; then public repo push |
| **13** | Limited real test, **max 20 files** | Test report; source files byte-identical (SHA verified before/after); **no production run** |
| **14** | Final audit vs Definition of Done | Every DoD item evidenced or honestly marked incomplete |

## 7. Non-negotiable boundaries (carried into every phase)

1. Never transcribe the full 13,126-file corpus. Max 20 real files, ever.
2. Never upload audio, transcripts, names, or chat exports anywhere.
3. Never call a cloud transcription API. Local inference only.
4. Source audio and chat exports are **read-only**: no delete, rename, move, overwrite, edit, or in-place convert. Verified by SHA-256 before/after in Phase 13.
5. Never guess a sender. Below the confidence threshold, the answer is "unknown".
6. Never label a filesystem timestamp as a WhatsApp timestamp.
7. Never claim completion before the installer and portable ZIP are built and smoke-tested.

## 8. Where each mandatory addendum deliverable lives

| Addendum §26 requirement | Document |
|---|---|
| 1. Final component diagram | `COMPONENT_ARCHITECTURE.md` |
| 2. Database migration plan | `DATABASE_MIGRATION_PLAN.md` |
| 3. Worker IPC contract | `WORKER_IPC_CONTRACT.md` |
| 4. Model registry format | `MODEL_REGISTRY.md` |
| 5. Transcript compatibility-key definition | `TRANSCRIPT_COMPATIBILITY_KEY.md` |
| 6. Export format examples | `COMPONENT_ARCHITECTURE.md` §7 + `SECOND_BRAIN_EXPORT.md` (Phase 8) |
| 7. Packaging matrix | `IMPLEMENTATION_PLAN.md` §4 + `RELEASE.md` (Phase 11) |
| 8. Test matrix mapped to every acceptance test | `TEST_MATRIX.md` |
