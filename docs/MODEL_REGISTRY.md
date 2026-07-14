# Model Registry Format

Implements `TECHNICAL_ADDENDUM.md` §6 and §26 deliverable 4.

---

## 1. Catalog (built into the app, version-controlled)

Only two models are exposed to the user (blueprint §4.2 step 4). Both are CTranslate2 conversions published by SYSTRAN, the maintainers of faster-whisper.

| Key | UI name | HF repo | Approx. download | Approx. RAM (int8) |
|---|---|---|---|---|
| `small` | **Small — Cepat, direkomendasikan** | `Systran/faster-whisper-small` | ~480 MB | ~1.0 GB |
| `medium` | **Medium — Lebih akurat, lebih lambat** | `Systran/faster-whisper-medium` | ~1.5 GB | ~2.6 GB |

Default: `small`. Medium is **never downloaded silently** (addendum §6.1).

The catalog also carries the required artifact file list per model:
`config.json`, `model.bin`, `tokenizer.json`, `vocabulary.txt` (plus `preprocessor_config.json` when present).

## 2. On-disk layout

```text
<data>/Models/
  registry.json                      ← the registry (below)
  small/
    config.json  model.bin  tokenizer.json  vocabulary.txt
    .dnt-manifest.json               ← per-file sha256 + sizes, written at install
  medium/
    ...
  .partial/                          ← downloads land here first; never a valid model dir
```

## 3. `registry.json`

```json
{
  "schema": 1,
  "updated_at": "2026-07-14T21:40:00+07:00",
  "models": {
    "small": {
      "display_name": "Small — Cepat, direkomendasikan",
      "engine_model_id": "small",
      "hf_repo": "Systran/faster-whisper-small",
      "local_folder": "small",
      "expected_size_bytes": 483183820,
      "min_ram_recommendation_bytes": 1073741824,
      "installed": true,
      "install_source": "download",
      "installed_at": "2026-07-14T21:38:11+07:00",
      "verification_state": "verified",
      "last_verified_at": "2026-07-14T21:38:44+07:00",
      "model_artifact_hash": "9c0a...e31f",
      "manifest": {
        "config.json":    {"size": 2263,      "sha256": "4f1c...9a02"},
        "model.bin":      {"size": 483546112, "sha256": "9c0a...e31f"},
        "tokenizer.json": {"size": 2202019,   "sha256": "b71d...44c8"},
        "vocabulary.txt": {"size": 460166,    "sha256": "0e5a...7712"}
      }
    },
    "medium": {
      "display_name": "Medium — Lebih akurat, lebih lambat",
      "engine_model_id": "medium",
      "hf_repo": "Systran/faster-whisper-medium",
      "local_folder": "medium",
      "expected_size_bytes": 1527000000,
      "min_ram_recommendation_bytes": 2684354560,
      "installed": false,
      "install_source": null,
      "installed_at": null,
      "verification_state": "not_installed",
      "last_verified_at": null,
      "model_artifact_hash": null,
      "manifest": {}
    }
  }
}
```

### Field meanings

| Field | Meaning |
|---|---|
| `expected_size_bytes` | Shown to the user **before** any download begins (addendum §6.2). |
| `installed` | A complete, atomically-renamed model folder exists. |
| `verification_state` | `not_installed` · `partial` · `verified` · `corrupt` |
| `model_artifact_hash` | **SHA-256 of `model.bin`.** This is the value that enters the transcript compatibility key. |
| `manifest` | Per-file size + SHA-256, computed locally at install. This is what "verify" re-checks. |
| `min_ram_recommendation_bytes` | Used to warn (not block) before selecting Medium on a low-RAM machine. |

## 4. Installation procedure (addendum §6.1–§6.7)

```text
1. User explicitly chooses a model. NEVER auto-download.
2. Show expected disk use + free disk space. Refuse if free space < size × 1.5.
3. Download every required file into  Models/.partial/<key>-<uuid>/
4. Compute SHA-256 of each downloaded file; write .dnt-manifest.json
5. Verify: all required files present, sizes > 0, model.bin loads a CTranslate2
   Whisper header  (cheap structural check, not a full inference)
6. os.replace(.partial/<key>-<uuid>  →  Models/<key>)   ← ATOMIC rename
7. If ANY step fails: delete the .partial dir, leave any previously valid model
   INTACT (addendum §6.6), report a safe message.
```

The `.partial` directory is inside `Models/`, so a crashed download is cleaned up at next startup and never leaves a half-model that the engine might load.

### Offline import (addendum §6.7)

`Unduh/Impor Model` also accepts `DifferentNetworkTranscribe-Model-Small.zip`:

```text
1. Open ZIP, reject absolute paths / "..\" entries (zip-slip guard)
2. Extract to Models/.partial/<key>-<uuid>/
3. Same verification + atomic rename as above
```

This is the path used on a machine with no internet, and it is why the release ships model ZIPs as assets.

## 5. Verification and startup

- On worker start: check `installed && verification_state == 'verified'` and that `model.bin` still matches `manifest["model.bin"].sha256` **by size only** (cheap). A full re-hash runs on "Periksa Integritas" or after a crash mid-write.
- If verification fails: worker state → `failed`, safe message `Model tidak ditemukan atau rusak.`, exit non-zero. The UI returns the user to model setup (addendum §6, final rule). **The queue is not marked failed** — this is a model-setup failure domain, not a transcription failure domain.

## 6. Git and release rules

- **Model weights are never committed to git** (blueprint §17.1, addendum §6.8). `Models/` is in `.gitignore`.
- Models are distributed as GitHub **Release assets**: `DifferentNetworkTranscribe-Model-Small.zip`, `DifferentNetworkTranscribe-Model-Medium.zip`.
- The release workflow fails if any asset ≥ 2 GiB (GitHub release-asset limit) or if any single git object ≥ 100 MiB.
- Medium ships only as a separate model pack, never inside the standard installer, because app + Medium approaches the release-asset limit (blueprint §18).

## 7. Interaction with the compatibility key

`model_artifact_hash` is one of the 11 compatibility-key fields. If a model is reinstalled and the artifact hash changes (upstream re-upload), previously completed transcripts are **still not requeued** — the changed hash only means new attempts will carry a different key. See `TRANSCRIPT_COMPATIBILITY_KEY.md` §4.
