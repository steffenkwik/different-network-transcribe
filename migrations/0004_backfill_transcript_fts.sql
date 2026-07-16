-- Existing completed records predating FTS synchronization become searchable
-- without retrancribing any source.  The database remains the authority.
INSERT OR REPLACE INTO transcript_fts(rowid, text)
SELECT a.id, COALESCE(mt.text, t.normalized_transcript, t.raw_transcript)
FROM audio_files AS a
JOIN transcription_attempts AS t ON t.id = a.preferred_transcript_id
LEFT JOIN manual_transcripts AS mt ON mt.id = a.preferred_manual_transcript_id
WHERE t.state = 'completed'
  AND COALESCE(mt.text, t.normalized_transcript, t.raw_transcript) IS NOT NULL;

INSERT OR REPLACE INTO transcript_fts_map(rowid, audio_file_id)
SELECT a.id, a.id
FROM audio_files AS a
JOIN transcription_attempts AS t ON t.id = a.preferred_transcript_id
WHERE t.state = 'completed'
  AND COALESCE(t.normalized_transcript, t.raw_transcript) IS NOT NULL;
