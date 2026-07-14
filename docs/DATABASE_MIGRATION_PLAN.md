# Database Migration Plan

Implements `PROJECT_BLUEPRINT.md` §11 and `TECHNICAL_ADDENDUM.md` §3, §26 deliverable 2.

Database: `<data>/Database/different_network_transcribe.sqlite3`

---

## 1. Connection configuration (every connection, every process)

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;      -- persistent; set once at creation
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```

Rules (addendum §3):
- **One connection per process/thread.** Connection objects are never shared.
- The worker is the single *processing* writer. The UI writes only user edits and settings, in short transactions.
- Long-running transactions are prohibited. Inference never runs inside a transaction.
- `PRAGMA quick_check` on every normal startup; `PRAGMA integrity_check` only on explicit "Periksa Integritas".
- All timestamps: **ISO 8601 with timezone** (`2026-07-14T20:31:00+07:00`). Displayed in local time.

## 2. Migration runner

```text
migrations/
  0001_initial.sql
  0002_<name>.sql
  ...
```

Algorithm:

```text
1. quick_check → abort on corruption, offer restore
2. read applied versions from app_schema_migrations
3. if pending migrations exist:
       a. BACKUP FIRST (mandatory, addendum §3.3) via sqlite3 backup API
          → Backups/pre-migration-<version>-<timestamp>.sqlite3
       b. for each pending migration in ascending order:
              BEGIN                               -- addendum §3.4
              execute statements
              INSERT INTO app_schema_migrations(version,name,applied_at,checksum)
              COMMIT                              -- on error: ROLLBACK, restore backup, abort
4. verify checksum of every already-applied migration file
       mismatch → refuse to start, report "skema tidak cocok" (tampered/edited migration)
```

`checksum` = SHA-256 of the migration file bytes. A previously-applied migration whose file later changes is an **error**, not a silent no-op.

Rollback: SQLite DDL is transactional, so a failed migration rolls back cleanly. If rollback itself fails, the pre-migration backup is restored to staging and swapped in. Tested by `test_rollback_after_failed_migration`.

## 3. `0001_initial.sql` — table set

All 16 tables from blueprint §11.1, verbatim in name and field intent.

| Table | Purpose | Key constraints |
|---|---|---|
| `app_schema_migrations` | version, name, applied_at, checksum | PK(version) |
| `source_roots` | audio + chat root folders | kind CHECK ∈ (audio, chat); UNIQUE(normalized_path) |
| `audio_files` | logical audio record | UNIQUE(stable_file_id); FK source_root_id; FK current_source_version_id; FK preferred_transcript_id |
| `audio_path_history` | every path a file has lived at | FK audio_file_id |
| `audio_source_versions` | one exact binary version | FK audio_file_id; UNIQUE(audio_file_id, sha256) |
| `chat_exports` | one .txt export | UNIQUE(source_root_id, relative_path); duplicate_of_id self-FK |
| `chat_voice_references` | one parsed "X sent file Y at T" line | FK chat_export_id |
| `metadata_matches` | candidate audio↔reference links | FK both sides; match_status CHECK |
| `manual_metadata_overrides` | human-corrected sender/chat/time | FK audio_file_id; `active` flag |
| `transcription_attempts` | immutable attempt history | FK audio_file_id, source_version_id; state CHECK |
| `manual_transcripts` | human transcript versions | FK audio_file_id, based_on_attempt_id |
| `processing_events` | append-only audit trail | FK audio_file_id NULLABLE |
| `worker_sessions` | lease + heartbeat | UNIQUE(instance_token) |
| `worker_commands` | UI→worker commands (IPC contract §5) | FK session_id |
| `export_runs` | export audit + output sha | — |
| `backups` | backup audit | — |
| `settings` | key → value_json | PK(key) |

Two tables beyond blueprint §11.1 are added because the addendum requires them:
- `worker_commands` — mandated by addendum §2 ("local command table in SQLite").
- `transcript_versions` is **not** added; blueprint's `transcription_attempts` + `manual_transcripts` already satisfy addendum §11 immutability, with `preferred_transcript_id` on `audio_files` as the explicit preferred-selection store.

### Immutability enforcement (addendum §11)

Transcript versions are immutable after creation. Enforced by SQL triggers, not just discipline:

```sql
CREATE TRIGGER trg_attempts_immutable_text
BEFORE UPDATE OF raw_transcript, normalized_transcript, segment_json,
                 model_name, model_hash, settings_json
ON transcription_attempts
WHEN OLD.state = 'completed'
BEGIN
    SELECT RAISE(ABORT, 'transcription_attempts row is immutable once completed');
END;

CREATE TRIGGER trg_manual_transcripts_immutable
BEFORE UPDATE OF text ON manual_transcripts
BEGIN
    SELECT RAISE(ABORT, 'manual_transcripts rows are immutable; create a new version');
END;
```

A manual edit **inserts a new row** and flips `active`; it never overwrites the previous manual version.

## 4. Indexes (blueprint §11.2)

```sql
CREATE INDEX idx_audio_state           ON audio_files(current_state);
CREATE INDEX idx_audio_norm_basename   ON audio_files(normalized_basename);
CREATE INDEX idx_audio_dupgroup        ON audio_files(duplicate_group);
CREATE UNIQUE INDEX idx_audio_stable   ON audio_files(stable_file_id);
CREATE INDEX idx_audio_root_relpath    ON audio_files(source_root_id, current_relative_path);
CREATE INDEX idx_versions_sha          ON audio_source_versions(sha256);
CREATE INDEX idx_versions_audio_cur    ON audio_source_versions(audio_file_id, is_current);
CREATE INDEX idx_refs_normfilename     ON chat_voice_references(normalized_filename);
CREATE INDEX idx_refs_export           ON chat_voice_references(chat_export_id);
CREATE INDEX idx_matches_audio         ON metadata_matches(audio_file_id, selected);
CREATE INDEX idx_matches_status        ON metadata_matches(match_status);
CREATE INDEX idx_attempts_audio        ON transcription_attempts(audio_file_id, attempt_number);
CREATE INDEX idx_attempts_state        ON transcription_attempts(state);
CREATE INDEX idx_attempts_version      ON transcription_attempts(source_version_id, state);
CREATE INDEX idx_events_audio          ON processing_events(audio_file_id, event_at);
CREATE INDEX idx_overrides_active      ON manual_metadata_overrides(audio_file_id, active);
```

### The list-view covering index

The "Semua Transkrip" table sorts by WhatsApp time and pages with `LIMIT/OFFSET`. To keep a page under 500 ms at 13,000 rows, the list query reads a **denormalized view** (`v_transcript_list`) that never selects a transcript body:

```sql
CREATE VIEW v_transcript_list AS
SELECT a.id, a.stable_file_id, a.current_state, a.basename, a.duration_seconds,
       COALESCE(o.sender,  r.sender_original)          AS sender,
       COALESCE(o.chat,    r.chat_original)            AS chat,
       COALESCE(o.whatsapp_message_at, r.whatsapp_message_at) AS whatsapp_message_at,
       (o.id IS NOT NULL)                              AS metadata_manually_corrected,
       m.match_status, m.confidence,
       t.model_name, t.quality_status, t.completed_at  AS last_processed_at
FROM audio_files a
LEFT JOIN manual_metadata_overrides o
       ON o.audio_file_id = a.id AND o.active = 1
LEFT JOIN metadata_matches m
       ON m.audio_file_id = a.id AND m.selected = 1
LEFT JOIN chat_voice_references r
       ON r.id = m.chat_voice_reference_id
LEFT JOIN transcription_attempts t
       ON t.id = a.preferred_transcript_id;
```

Transcript bodies are fetched **only** when a detail drawer opens (blueprint §22: lazy transcript loading, no full transcript loading on startup).

## 5. Full-text search

Bundled SQLite is **3.49.1 with FTS5 available** (verified this session), so FTS5 is used:

```sql
CREATE VIRTUAL TABLE transcript_fts USING fts5(
    text,
    content='',              -- contentless: we store the text once, in the attempt row
    tokenize='unicode61 remove_diacritics 2'
);
CREATE TABLE transcript_fts_map (rowid INTEGER PRIMARY KEY, audio_file_id INTEGER NOT NULL);
```

The FTS index is populated **only** from the preferred transcript, and updated when the preferred transcript changes. FTS queries run **only when the user explicitly searches transcript text** (blueprint §22).

**Documented fallback** (required by blueprint §11.2 in case a future bundled SQLite lacks FTS5): `MigrationRunner` probes for FTS5 at startup; if absent it sets `settings['fts_mode']='like'` and transcript search degrades to an indexed `LIKE '%term%'` scan over `normalized_transcript`, with a UI notice that search is slower. Correctness is unchanged; only speed differs.

## 6. Backup consistency (addendum §18)

Never copy the `.sqlite3` file while ignoring WAL state. Backup always uses the **SQLite online backup API**:

```python
with sqlite3.connect(dest) as dst:
    src.backup(dst)          # consistent snapshot, safe while the worker writes
```

Manifest (`manifest.json` inside the `.dntbackup`) records: database SHA-256, schema version, app version, creation time, included components, model manifests, export manifests.

Restore uses **staging**: extract → validate manifest → `integrity_check` on the staged DB → back up the current live DB → swap only after success. Never overwrite the live DB in place.

## 7. Migration test set (Phase 2 gate)

| Test | Asserts |
|---|---|
| `test_initial_migration` | All 17 tables + indexes + triggers created; `PRAGMA foreign_keys=ON` |
| `test_upgrade_migration` | 0001 → 0002 applies once; re-run is a no-op |
| `test_rollback_after_failed_migration` | Deliberately broken 0002 ⇒ transaction rolls back, DB still at 0001, backup exists |
| `test_migration_checksum_tamper` | Editing an applied migration file ⇒ startup refuses |
| `test_wal_configured` | `journal_mode == 'wal'`, `synchronous == 1` |
| `test_foreign_keys_enforced` | Orphan insert raises `IntegrityError` |
| `test_immutable_attempt_trigger` | Updating a completed attempt's text raises |
| `test_13000_synthetic_records` | Insert 13,000 rows; first page < 1 s; paged query < 500 ms; filter < 1 s |
| `test_fts_search` | FTS5 finds a term; fallback path also finds it |
| `test_stale_worker_recovery` | Interrupted `processing` → `queued`; completed untouched; history preserved |
| `test_concurrent_read_while_worker_writes` | Reader is never blocked > busy_timeout |
| `test_duplicate_worker_prevention` | Second lease acquisition fails |
| `test_backup_restore_roundtrip` | Backup while writing; restore; `integrity_check` ok; row counts equal |
