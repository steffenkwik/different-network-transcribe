-- P0-5: an FTS5 `content=''` table cannot forget anything.
--
-- `INSERT OR REPLACE INTO transcript_fts(rowid, text)` added the new tokens but
-- left every token of the previous transcript indexed, so after a reprocess or
-- a manual correction, searching transcript bodies still matched text that no
-- longer existed anywhere in the database.
--
-- `contentless_delete=1` (SQLite 3.43+) makes the row genuinely deletable, and
-- an INSERT OR REPLACE against it removes the old tokens first. The index is
-- derived data: it is dropped and rebuilt from the authoritative preferred
-- transcripts. No audio is read and no transcript is recomputed.
DROP TABLE IF EXISTS transcript_fts;

CREATE VIRTUAL TABLE transcript_fts USING fts5(
    text,
    content='',
    contentless_delete=1,
    tokenize='unicode61 remove_diacritics 2'
);

DELETE FROM transcript_fts_map;

INSERT INTO transcript_fts(rowid, text)
SELECT a.id, COALESCE(mt.text, t.normalized_transcript, t.raw_transcript)
FROM audio_files AS a
JOIN transcription_attempts AS t ON t.id = a.preferred_transcript_id
LEFT JOIN manual_transcripts AS mt ON mt.id = a.preferred_manual_transcript_id
WHERE t.state = 'completed'
  AND COALESCE(mt.text, t.normalized_transcript, t.raw_transcript) IS NOT NULL;

INSERT INTO transcript_fts_map(rowid, audio_file_id)
SELECT a.id, a.id
FROM audio_files AS a
JOIN transcription_attempts AS t ON t.id = a.preferred_transcript_id
LEFT JOIN manual_transcripts AS mt ON mt.id = a.preferred_manual_transcript_id
WHERE t.state = 'completed'
  AND COALESCE(mt.text, t.normalized_transcript, t.raw_transcript) IS NOT NULL;
