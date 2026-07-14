CREATE TABLE app_schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    checksum TEXT NOT NULL
);

CREATE TABLE source_roots (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('audio', 'chat')),
    original_path TEXT NOT NULL,
    normalized_path TEXT NOT NULL UNIQUE,
    volume_identifier TEXT,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    last_scanned_at TEXT
);

CREATE TABLE audio_files (
    id INTEGER PRIMARY KEY,
    stable_file_id TEXT NOT NULL UNIQUE,
    source_root_id INTEGER NOT NULL REFERENCES source_roots(id),
    current_relative_path TEXT NOT NULL,
    basename TEXT NOT NULL,
    normalized_basename TEXT NOT NULL,
    extension TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
    windows_created_at TEXT,
    windows_modified_at TEXT,
    first_discovered_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    duration_seconds REAL,
    sha256 TEXT,
    readable INTEGER NOT NULL DEFAULT 1 CHECK(readable IN (0, 1)),
    zero_byte INTEGER NOT NULL DEFAULT 0 CHECK(zero_byte IN (0, 1)),
    duplicate_group TEXT,
    current_source_version_id INTEGER REFERENCES audio_source_versions(id),
    current_state TEXT NOT NULL DEFAULT 'discovered',
    preferred_transcript_id INTEGER REFERENCES transcription_attempts(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE audio_path_history (
    id INTEGER PRIMARY KEY,
    audio_file_id INTEGER NOT NULL REFERENCES audio_files(id) ON DELETE CASCADE,
    source_root_id INTEGER NOT NULL REFERENCES source_roots(id),
    relative_path TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    UNIQUE(audio_file_id, source_root_id, relative_path)
);

CREATE TABLE audio_source_versions (
    id INTEGER PRIMARY KEY,
    audio_file_id INTEGER NOT NULL REFERENCES audio_files(id) ON DELETE CASCADE,
    size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
    modified_at TEXT,
    sha256 TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    stale_at TEXT,
    is_current INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0, 1)),
    UNIQUE(audio_file_id, sha256)
);

CREATE TABLE chat_exports (
    id INTEGER PRIMARY KEY,
    source_root_id INTEGER NOT NULL REFERENCES source_roots(id),
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    inferred_chat_name TEXT,
    parser_version TEXT,
    first_discovered_at TEXT NOT NULL,
    last_parsed_at TEXT,
    duplicate_of_id INTEGER REFERENCES chat_exports(id),
    parse_status TEXT NOT NULL DEFAULT 'pending',
    warning_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(source_root_id, relative_path)
);

CREATE TABLE chat_voice_references (
    id INTEGER PRIMARY KEY,
    chat_export_id INTEGER NOT NULL REFERENCES chat_exports(id) ON DELETE CASCADE,
    line_number INTEGER NOT NULL,
    sender_original TEXT,
    chat_original TEXT,
    whatsapp_message_at TEXT,
    referenced_filename TEXT,
    normalized_filename TEXT,
    parser_pattern TEXT,
    parser_confidence REAL NOT NULL DEFAULT 0 CHECK(parser_confidence BETWEEN 0 AND 1),
    warning TEXT,
    header_hash TEXT NOT NULL,
    UNIQUE(chat_export_id, line_number)
);

CREATE TABLE metadata_matches (
    id INTEGER PRIMARY KEY,
    audio_file_id INTEGER NOT NULL REFERENCES audio_files(id) ON DELETE CASCADE,
    chat_voice_reference_id INTEGER NOT NULL REFERENCES chat_voice_references(id) ON DELETE CASCADE,
    match_status TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
    evidence_json TEXT NOT NULL DEFAULT '{}',
    selected INTEGER NOT NULL DEFAULT 0 CHECK(selected IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(audio_file_id, chat_voice_reference_id)
);

CREATE TABLE manual_metadata_overrides (
    id INTEGER PRIMARY KEY,
    audio_file_id INTEGER NOT NULL REFERENCES audio_files(id) ON DELETE CASCADE,
    sender TEXT,
    chat TEXT,
    whatsapp_message_at TEXT,
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1))
);

CREATE TABLE worker_sessions (
    id INTEGER PRIMARY KEY,
    instance_token TEXT NOT NULL UNIQUE,
    pid INTEGER,
    started_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    requested_action TEXT,
    state TEXT NOT NULL CHECK(state IN ('idle', 'starting', 'running', 'pausing', 'paused', 'stopping', 'stopped', 'failed')),
    stopped_at TEXT
);

CREATE TABLE transcription_attempts (
    id INTEGER PRIMARY KEY,
    audio_file_id INTEGER NOT NULL REFERENCES audio_files(id) ON DELETE CASCADE,
    source_version_id INTEGER NOT NULL REFERENCES audio_source_versions(id),
    worker_session_id INTEGER REFERENCES worker_sessions(id),
    model_name TEXT NOT NULL,
    model_hash TEXT,
    engine_name TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    language TEXT NOT NULL,
    settings_json TEXT NOT NULL,
    compat_key TEXT NOT NULL,
    attempt_number INTEGER NOT NULL CHECK(attempt_number > 0),
    state TEXT NOT NULL CHECK(state IN ('queued', 'processing', 'completed', 'failed', 'interrupted', 'no_speech')),
    started_at TEXT,
    completed_at TEXT,
    processing_seconds REAL,
    detected_language TEXT,
    language_probability REAL,
    raw_transcript TEXT,
    normalized_transcript TEXT,
    segment_json TEXT,
    error_type TEXT,
    safe_error_message TEXT,
    technical_log_reference TEXT,
    quality_status TEXT,
    quality_score REAL,
    quality_reasons_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE(audio_file_id, attempt_number)
);

CREATE TABLE manual_transcripts (
    id INTEGER PRIMARY KEY,
    audio_file_id INTEGER NOT NULL REFERENCES audio_files(id) ON DELETE CASCADE,
    based_on_attempt_id INTEGER REFERENCES transcription_attempts(id),
    creator_type TEXT NOT NULL DEFAULT 'manual' CHECK(creator_type IN ('manual', 'imported')),
    text TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0 CHECK(verified IN (0, 1)),
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    selected_as_preferred_at TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1))
);

CREATE TABLE processing_events (
    id INTEGER PRIMARY KEY,
    audio_file_id INTEGER REFERENCES audio_files(id) ON DELETE SET NULL,
    session_id TEXT,
    event_type TEXT NOT NULL,
    event_at TEXT NOT NULL,
    safe_message TEXT,
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE worker_commands (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES worker_sessions(id) ON DELETE CASCADE,
    command TEXT NOT NULL CHECK(command IN ('start', 'pause', 'resume', 'safe_stop', 'retry_failed', 'reprocess_selected', 'shutdown')),
    payload_json TEXT,
    issued_at TEXT NOT NULL,
    acknowledged_at TEXT,
    completed_at TEXT,
    result TEXT
);

CREATE TABLE export_runs (
    id INTEGER PRIMARY KEY,
    format TEXT NOT NULL,
    options_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    record_count INTEGER,
    output_path TEXT,
    output_sha256 TEXT,
    status TEXT NOT NULL,
    error TEXT
);

CREATE TABLE backups (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    backup_path TEXT NOT NULL,
    manifest_sha256 TEXT,
    database_integrity_result TEXT,
    app_version TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_audio_state ON audio_files(current_state);
CREATE INDEX idx_audio_norm_basename ON audio_files(normalized_basename);
CREATE INDEX idx_audio_dupgroup ON audio_files(duplicate_group);
CREATE INDEX idx_audio_root_relpath ON audio_files(source_root_id, current_relative_path);
CREATE INDEX idx_versions_sha ON audio_source_versions(sha256);
CREATE INDEX idx_versions_audio_current ON audio_source_versions(audio_file_id, is_current);
CREATE INDEX idx_refs_normfilename ON chat_voice_references(normalized_filename);
CREATE INDEX idx_refs_export ON chat_voice_references(chat_export_id);
CREATE INDEX idx_matches_audio ON metadata_matches(audio_file_id, selected);
CREATE INDEX idx_matches_status ON metadata_matches(match_status);
CREATE INDEX idx_attempts_audio ON transcription_attempts(audio_file_id, attempt_number);
CREATE INDEX idx_attempts_state ON transcription_attempts(state);
CREATE INDEX idx_attempts_version ON transcription_attempts(source_version_id, state);
CREATE INDEX idx_events_audio ON processing_events(audio_file_id, event_at);
CREATE INDEX idx_overrides_active ON manual_metadata_overrides(audio_file_id, active);
CREATE INDEX idx_worker_commands_pending ON worker_commands(session_id, acknowledged_at);

CREATE UNIQUE INDEX idx_matches_one_selected_per_audio
    ON metadata_matches(audio_file_id) WHERE selected = 1;
CREATE UNIQUE INDEX idx_versions_one_current_per_audio
    ON audio_source_versions(audio_file_id) WHERE is_current = 1;
CREATE UNIQUE INDEX idx_overrides_one_active_per_audio
    ON manual_metadata_overrides(audio_file_id) WHERE active = 1;
CREATE UNIQUE INDEX idx_manual_transcripts_one_active_per_audio
    ON manual_transcripts(audio_file_id) WHERE active = 1;

CREATE VIRTUAL TABLE transcript_fts USING fts5(
    text,
    content='',
    tokenize='unicode61 remove_diacritics 2'
);
CREATE TABLE transcript_fts_map (
    rowid INTEGER PRIMARY KEY,
    audio_file_id INTEGER NOT NULL UNIQUE REFERENCES audio_files(id) ON DELETE CASCADE
);

CREATE VIEW v_transcript_list AS
SELECT
    a.id,
    a.stable_file_id,
    a.current_state,
    a.basename,
    a.normalized_basename,
    a.duration_seconds,
    COALESCE(o.sender, r.sender_original) AS sender,
    COALESCE(o.chat, r.chat_original) AS chat,
    COALESCE(o.whatsapp_message_at, r.whatsapp_message_at) AS whatsapp_message_at,
    (o.id IS NOT NULL) AS metadata_manually_corrected,
    m.match_status,
    m.confidence,
    t.model_name,
    t.quality_status,
    t.completed_at AS last_processed_at
FROM audio_files a
LEFT JOIN manual_metadata_overrides o ON o.audio_file_id = a.id AND o.active = 1
LEFT JOIN metadata_matches m ON m.audio_file_id = a.id AND m.selected = 1
LEFT JOIN chat_voice_references r ON r.id = m.chat_voice_reference_id
LEFT JOIN transcription_attempts t ON t.id = a.preferred_transcript_id;

CREATE TRIGGER trg_attempts_immutable_text
BEFORE UPDATE OF raw_transcript, normalized_transcript, segment_json, model_name, model_hash, settings_json, compat_key
ON transcription_attempts
WHEN OLD.state = 'completed'
BEGIN
    SELECT RAISE(ABORT, 'transcription_attempts row is immutable once completed');
END;

CREATE TRIGGER trg_manual_transcripts_immutable_text
BEFORE UPDATE OF text ON manual_transcripts
BEGIN
    SELECT RAISE(ABORT, 'manual_transcripts rows are immutable; create a new version');
END;
