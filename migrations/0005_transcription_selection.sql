-- A user may explicitly leave discovered audio out of a future worker run.
-- Existing records default to enabled so this migration never changes a queue
-- merely by being installed.  Completed rows retain their no-repeat behaviour.
ALTER TABLE audio_files
    ADD COLUMN transcription_enabled INTEGER NOT NULL DEFAULT 1
    CHECK(transcription_enabled IN (0, 1));

CREATE INDEX idx_audio_selection_queue
    ON audio_files(source_root_id, transcription_enabled, current_state);
