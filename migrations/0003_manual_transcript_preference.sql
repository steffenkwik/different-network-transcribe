-- A human correction is a new immutable version.  It never overwrites the
-- Faster-Whisper attempt that it corrects, and the selected manual version is
-- explicit rather than inferred from a filename or model setting.
ALTER TABLE audio_files
    ADD COLUMN preferred_manual_transcript_id INTEGER REFERENCES manual_transcripts(id);

CREATE INDEX idx_audio_preferred_manual_transcript
    ON audio_files(preferred_manual_transcript_id);
