# Worker IPC Contract

Implements `TECHNICAL_ADDENDUM.md` §2 and §26 deliverable 3. Binding contract between the UI process and the transcription worker process.

---

## 1. Design choice

The addendum permits "a local command table in SQLite **or** a local named pipe". **We use the SQLite command table**, plus an atomically-written status file for high-frequency progress.

| Channel | Carries | Why |
|---|---|---|
| **SQLite `worker_sessions`** | lease, PID, instance token, heartbeat, state | Durable. Survives a crash on either side. Enables stale-lease detection with no OS-specific pipe cleanup. |
| **SQLite `worker_commands`** | `start`, `pause`, `resume`, `safe_stop`, `retry_failed`, `reprocess_selected`, `shutdown` | Durable and replay-safe. A command issued just before a UI crash is still honoured. |
| **SQLite record rows** | per-file results, attempts, quality | The source of truth. Committed per file. |
| **`Temp/worker_status.json`** | current file, counts, ETA, phase | High-frequency progress **without** hammering the DB with writes. Written atomically ≤ 1×/second. |

**No named pipe. No socket. No local web server. No internet.**

**Transcript bodies are never sent through IPC.** The worker writes them to SQLite and the status file references only the `audio_file_id` and stable ID. (Addendum §2, final rule.)

## 2. Timing constants

| Constant | Value | Source |
|---|---|---|
| UI poll interval | 750 ms | addendum §2 (500–1000 ms) |
| Worker heartbeat | 2 s | addendum §2 |
| Lease timeout (stale after) | 10 s | addendum §2 |
| Status file write | max 1×/s (rate-limited) | addendum §2 "rate-limited to avoid excessive DB writes" |
| Command poll (worker) | every 1 s, **and** at every file boundary | ensures pause/stop feels immediate |
| `PRAGMA busy_timeout` | 5000 ms | addendum §3 |

## 3. Worker launch

| Context | Command |
|---|---|
| Frozen (PyInstaller) | `DifferentNetworkTranscribe.exe --worker --data-dir "<path>" --session <instance_token>` |
| Development | `python -m worker.main --worker --data-dir "<path>" --session <instance_token>` |

`app/main.py` inspects `--worker` **before** importing PySide6, so the worker process never loads Qt.

The parent passes no private data on the command line — only a data directory and an opaque token.

## 4. Lease protocol (single-writer guarantee)

Blueprint §6.3. Only one production worker may operate on a database.

**Acquire (UI, before spawning):**

```sql
BEGIN IMMEDIATE;
-- a lease is live if it is not stopped and its heartbeat is younger than 10 s
SELECT id FROM worker_sessions
 WHERE state NOT IN ('stopped','failed')
   AND heartbeat_at > datetime('now','-10 seconds');
-- if a row is returned → ABORT, show "Proses transkripsi sudah berjalan."
INSERT INTO worker_sessions (instance_token, pid, started_at, heartbeat_at, state)
VALUES (?, ?, ?, ?, 'starting');
COMMIT;
```

`BEGIN IMMEDIATE` takes the write lock, so two UIs racing cannot both win. Tested by `test_duplicate_worker_prevention`.

**Heartbeat (worker, every 2 s):** `UPDATE worker_sessions SET heartbeat_at = ?, state = ? WHERE instance_token = ?`

**Stale-lease recovery (UI, at startup):**

```text
for each session with state NOT IN ('stopped','failed')
        AND heartbeat_at older than 10 s:
    mark session state = 'failed', stopped_at = now
    for each attempt in state 'processing' owned by that session:
        attempt.state = 'interrupted'            -- history PRESERVED, never deleted
        audio_file.current_state = 'queued'      -- ONLY the interrupted row is requeued
    -- completed rows are untouched. The queue is never globally reset.
```

## 5. Command table

```sql
CREATE TABLE worker_commands (
    id            INTEGER PRIMARY KEY,
    session_id    INTEGER REFERENCES worker_sessions(id) ON DELETE CASCADE,
    command       TEXT NOT NULL CHECK (command IN
                    ('start','pause','resume','safe_stop',
                     'retry_failed','reprocess_selected','shutdown')),
    payload_json  TEXT,          -- e.g. {"audio_file_ids":[12,44], "model":"medium"}
    issued_at     TEXT NOT NULL,
    acknowledged_at TEXT,
    completed_at  TEXT,
    result        TEXT
);
CREATE INDEX idx_worker_commands_pending
    ON worker_commands(session_id, acknowledged_at);
```

The worker consumes the oldest unacknowledged command for its own `session_id`, sets `acknowledged_at` immediately, and sets `completed_at` when the resulting state change is durable.

`reprocess_selected` payload is the **only** way a completed file gets a new attempt (blueprint §13, addendum §5).

## 6. Worker state machine

```text
        ┌──────┐  start   ┌──────────┐        ┌─────────┐
        │ idle ├─────────►│ starting ├───────►│ running │◄──────┐
        └──────┘          └────┬─────┘        └────┬────┘       │ resume
                               │ model load        │ pause      │
                               │ FAILS             ▼            │
                               ▼             ┌──────────┐  ┌────┴───┐
                          ┌────────┐         │ pausing  ├─►│ paused │
                          │ failed │         └──────────┘  └────────┘
                          └────────┘              │ safe_stop / shutdown
                                                  ▼
                                          ┌──────────┐   ┌─────────┐
                                          │ stopping ├──►│ stopped │
                                          └──────────┘   └─────────┘
```

States: `idle`, `starting`, `running`, `pausing`, `paused`, `stopping`, `stopped`, `failed` — exactly the addendum §2 list.

- **`pausing` → `paused`:** stop assigning new files; **finish the current file**; commit; release nothing. Ready to resume.
- **`stopping` → `stopped`:** stop assigning; finish or safely release the current record; commit; **release the lease**; write final status; exit 0.
- Transition to `failed` (e.g. model missing) writes a safe message and exits non-zero; the UI routes the user back to model setup.

## 7. `worker_status.json`

Written atomically (`temp → os.replace`) at most once per second to `<data>/Temp/worker_status.json`.

```json
{
  "schema": 1,
  "instance_token": "b3f1c2a9-...",
  "pid": 24188,
  "state": "running",
  "updated_at": "2026-07-14T21:03:11+07:00",
  "model": "small",
  "model_loaded": true,
  "model_load_count": 1,
  "session_started_at": "2026-07-14T20:58:02+07:00",
  "current": {
    "audio_file_id": 8123,
    "stable_id": "a81f29c2",
    "basename": "PTT-20260714-WA0043.opus",
    "duration_seconds": 18.4,
    "started_at": "2026-07-14T21:03:07+07:00"
  },
  "counts": {
    "queued": 412, "completed_session": 63, "failed_session": 2,
    "skipped_complete_session": 19, "total_pending": 412
  },
  "eta": {
    "available": true,
    "seconds_remaining": 5220,
    "basis": "observed_realtime_factor",
    "samples": 63
  },
  "last_safe_message": null
}
```

Contract points:
- `basename` is the audio filename, which is not private content. **No sender name, no chat title, no transcript text ever appears in this file.**
- `model_load_count` must remain `1` for a whole session. `test_model_loaded_once` asserts it.
- `eta.available` is `false` until at least **5** completed samples exist (blueprint §22: "Do not provide a misleading ETA after only one file"). ETA is computed from the observed real-time factor (processing seconds ÷ audio seconds) applied to the remaining **audio duration**, not the remaining file count.
- If the file is missing or stale (`updated_at` older than 10 s), the UI treats the worker as dead and runs stale-lease recovery. The DB, not this file, is authoritative.

## 8. Per-file transaction boundary

One short transaction per file (addendum §3.1) — never one big transaction over the queue:

```text
claim:    BEGIN IMMEDIATE
            re-verify no-repeat (source exists, sha matches, no completed attempt)
            INSERT transcription_attempts (state='processing', session_id, started_at)
            UPDATE audio_files SET current_state='processing'
          COMMIT
decode + transcribe + quality-check      ← NO transaction held open here
commit:   BEGIN IMMEDIATE
            UPDATE transcription_attempts SET state='completed'|'failed', ...
            UPDATE audio_files SET current_state=..., preferred_transcript_id=...
            INSERT processing_events (...)
          COMMIT
```

The long-running inference happens with **no open transaction**, so the UI can always read and write settings/edits concurrently (WAL + `busy_timeout`).

## 9. Failure and shutdown semantics

| Event | Result |
|---|---|
| One file fails to decode | attempt `failed`, safe message stored, `attempt_number` incremented, **queue continues** |
| Worker process killed (Task Manager / power loss) | lease goes stale in 10 s; next UI start marks the attempt `interrupted` and requeues **only that file** |
| UI process killed while worker runs | worker keeps running; on next UI start the live lease is detected and the UI re-attaches to the running worker |
| Model file missing/corrupt | state `failed`, safe message `Model tidak ditemukan atau rusak.`, exit → UI opens model setup |
| DB locked > 5 s | retry with backoff; after 3 failures the file is released back to `queued` and the worker reports a warning |
| `shutdown` command | equivalent to `safe_stop` then process exit |

Automatic retries: **1** for transient errors (decode timeout, transient I/O), default from config. Never an infinite retry loop. Manual retry is always available.
