CREATE INDEX idx_audio_state_basename ON audio_files(current_state, normalized_basename);
CREATE INDEX idx_chat_exports_duplicate ON chat_exports(duplicate_of_id);
CREATE INDEX idx_worker_sessions_heartbeat ON worker_sessions(state, heartbeat_at);
