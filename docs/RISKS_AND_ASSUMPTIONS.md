# Risks and Assumptions

Phase 0 deliverable (blueprint §24). Honest register. Updated as risks are retired or discovered.

---

## 1. Risks

| ID | Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|---|
| **R-01** | **Accidental mass retranscription.** A future change makes a settings/model/engine difference invalidate completed transcripts, retranscribing 13,126 files (days of CPU). | **Critical** | Medium — this is the easiest mistake to make | `TRANSCRIPT_COMPATIBILITY_KEY.md` §3 forbids compat-key-driven requeue. `test_compat_key_not_consulted_in_reuse_check` fails the build if `may_reuse()` ever references `compat_key`. Reprocess triggers are a closed list of 5. |
| **R-02** | **`<Media omitted>` exports.** If the chat exports were made *without* media, they contain no filename, so exact sender matching is impossible for those chats. | High — could affect a large share of the 13,126 | Medium–High (unknown until Phase 4 measures it) | Never fabricate. Record `filename_not_present`, sender = unknown, route to review. **Phase 4 will report the real ratio** of exports containing filenames vs `<Media omitted>` so expectations are set with data, not hope. |
| **R-03** | **Private data leaking into a public GitHub repo.** Git history is permanent. | **Critical** | Low, given controls | `.gitignore` written before any code. Synthetic fixtures only. Private-data scanner (Phase 12) runs before first push. Repo stays local until it passes. |
| **R-04** | Transcription throughput. Small/int8 on 16 threads ≈ 4–8× real-time. 13,126 voice notes at ~20 s average ≈ 73 h of audio ⇒ roughly **10–20 hours** of wall time. | Medium — expectation risk, not a defect | High | Communicate honestly in the UI (ETA from *observed* real-time factor after ≥5 samples, never after 1 file). Pause/resume makes a multi-day run safe. |
| **R-05** | 109 zero-byte files in the real corpus. | Low | Certain (measured) | Scanner marks `zero_byte=1`, `readable=0`; they are excluded from the queue and surfaced in "Perlu Diperiksa" rather than failing repeatedly. |
| **R-06** | Whisper hallucination on silence/noise (known model behaviour: repeated phrases, invented generic sentences). | Medium — wrong content in a second brain | High for noisy VNs | `vad_filter=true`, `condition_on_previous_text=false`, `temperature=0.0`, plus quality checks for repetition loops, mostly-punctuation, and long-audio/tiny-text. Flagged → review, never silently trusted. |
| **R-07** | Unsigned installer ⇒ Windows SmartScreen warning. | Medium — team friction | Certain (no certificate) | Documented in README + user guide with the exact click path. Blueprint §18 explicitly permits unsigned for internal v1. |
| **R-08** | PyInstaller misses a native DLL (CTranslate2 / PyAV / Qt plugins) ⇒ app runs in dev but not when packaged. | High — breaks the whole delivery | Medium | One-folder build (not one-file); the packaging gate runs the built exe with **PATH scrubbed of Python** on a clean location. Failure here blocks release. |
| **R-09** | `%LOCALAPPDATA%` install + user data in Documents: an antivirus or corporate policy blocks writes. | Low | Low | Data folder is user-selectable at first run; portable build asks for a writable directory and never writes inside the app folder. |
| **R-10** | Long paths / Unicode names in the real corpus break output writing. | Medium | Medium (110 subfolders, WhatsApp names) | Windows-safe normalization + `\\?\` long-path prefix + reserved-name handling, tested in `test_windows_reserved_names`, `test_long_path`. |
| **R-11** | Duplicate basenames across chats (`PTT-...WA0043.opus` recurs). Matching on basename alone would attach the wrong sender. | High — wrong attribution is worse than no attribution | High | Addendum §4.7: filename alone is never proof. SHA-256 is the identity authority; `duplicate_group` is tracked; ambiguity ⇒ unknown + review. |
| **R-12** | Model download (~2 GB for both) fails midway or corrupts. | Medium | Medium | Download to `.partial`, verify SHA-256 per file, atomic rename, previous valid model preserved on failure. Offline ZIP import as the fallback path. |
| **R-13** | 13,000-row UI freeze. | High — blueprint §22 explicitly forbids | Medium if done naively | Paged queries against a covering view that never selects transcript bodies; lazy detail loading; measured against the addendum §22 thresholds and recorded. |

## 2. Assumptions (to be confirmed, not silently relied on)

| ID | Assumption | How it will be confirmed | If wrong |
|---|---|---|---|
| **A-01** | The 353 `.txt` files are WhatsApp chat exports in a supported format. | Phase 4 parses them and reports pattern-match rates. | Parser gains a new pattern ID; parser is versioned for exactly this. |
| **A-02** | A meaningful share of exports include media filenames (`PTT-....opus (file attached)`). | Phase 4 reports the exact ratio. | R-02 materialises: most records legitimately have unknown senders. Product still works; expectations change. |
| **A-03** | The `.opus` files are decodable by PyAV without external FFmpeg. | Phase 6 decodes the ≤20 test files. | Bundle an LGPL FFmpeg per blueprint §19 and preserve notices. |
| **A-04** | Indonesian (`language="id"`) is correct for effectively all voice notes. | Phase 13 checks `language_probability` on the 20 real files. | Offer "Otomatis" language setting (already in blueprint §5.4). |
| **A-05** | 20 files is enough to validate the pipeline before the user's own production run. | Phase 13 report. | The user runs a larger batch themselves — the agent still never does. |
| **A-06** | Team members install per-user without admin rights. | Phase 11 clean-install test into a sandboxed `%LOCALAPPDATA%`. | Provide a machine-wide installer variant. |

## 3. Explicitly accepted limitations (stated to the user, not hidden)

1. **The sender cannot be identified from audio.** No voice biometrics, ever (blueprint §2.2). Sender comes from the chat export or it is unknown.
2. **No model is perfect.** Small is fast; Medium is more accurate and much slower. Both results are preserved; a human decides.
3. **A Windows file timestamp is not a WhatsApp timestamp.** Copying files changes creation time. The two are never conflated, and `Tanggal File` is a forbidden label.
4. **Exports are derived artifacts.** Deleting them is always safe; SQLite rebuilds them without touching audio.
