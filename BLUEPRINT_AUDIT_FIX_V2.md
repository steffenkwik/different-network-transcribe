# DIFFERENT NETWORK TRANSCRIBE — BLUEPRINT AUDIT & PERBAIKAN v2

**Status dokumen:** Spesifikasi perbaikan otoritatif (hasil audit independen atas kode v0.2.0)
**Disusun:** 2026-07-17, oleh audit Claude (Fable)
**Dieksekusi oleh:** Claude Opus (atau coding agent setara yang repository-aware)
**Basis kode:** repo ini, commit `e21fc31` — 147 unit test lulus; bug yang tercantum di sini adalah bug desain/alur yang TIDAK tercakup test
**Sifat pekerjaan:** AUDIT & FIX — **bukan tulis ulang dari awal.** Arsitektur (PySide6 + SQLite + faster-whisper + worker terpisah) dipertahankan.

## STATUS EKSEKUSI

| Fase | Isi | Status |
|---|---|---|
| **1** | P0-1 … P0-7 (fungsi rusak) | ✅ **SELESAI** 2026-07-17 |
| **2** | P1-1 … P1-4 (skala ribuan) | ✅ **SELESAI** 2026-07-17 |
| **3** | Settings lengkap + model Turbo + mode translate | ✅ **SELESAI** 2026-07-17 (sisa polish §5.3 di bawah) |
| 4 | Rilis v0.3.0 | ⬜ belum — butuh keputusan pemilik |
| 5 | GPU Vulkan (opsional) | ⬜ belum |

### Sisa yang sengaja belum dikerjakan (kandidat Fase 4)

Setting berikut **masih ada di config tetapi belum dikonsumsi**. Sesuai aturan "setiap
setting yang tampil harus berefek", semuanya **tidak ditampilkan di UI** sehingga tidak
ada yang berbohong kepada pengguna. Pilihannya: implementasikan atau hapus dari config.

| Field | Kondisi | Rekomendasi |
|---|---|---|
| `ui.theme` | mati | butuh stylesheet gelap; implementasikan atau hapus field-nya |
| `transcription.review_model` | mati | sambungkan ke pilihan model pada "Proses Ulang" di dialog detail |
| `transcription.retry_limit` | mati | butuh logika retry otomatis di worker |
| `backup.*`, `diagnostics.*` | dikonsumsi sebagian | audit ulang saat Fase 4 |

Polish §5.3 yang belum: pilihan model saat "Proses Ulang", opsi ketiga pada `closeEvent`
("tutup UI, biarkan worker jalan"), unduh Small langsung dari wizard, fallback dekode
`.opus` untuk `QMediaPlayer` di Windows lama.

**Bukti per 2026-07-17:** 215 test lulus (dari 147), ruff + mypy bersih, self-test UI PASS.

**End-to-end nyata dengan engine dan model asli** (bukan fake):
1. 3 file audio asli ditranskripsi benar dengan model Small (`cpu_threads=11`, batched
   aktif, 2,8 dtk/file untuk audio 22,5 dtk ≈ 8× realtime); sumber terbukti tidak berubah;
   ekspor Markdown terbentuk; kartu dashboard menjumlah tepat.
2. Mode `transcribe`, `translate`, dan fallback non-batched ketiganya menghasilkan
   transkrip pada engine asli.
3. **Rantai setting terbukti utuh**: `save_transcription_settings()` (persis yang dipanggil
   halaman Pengaturan) → config.toml → worker → engine. Semua nilai (`task=translate`,
   `language=auto`, batching mati, VAD mati, `beam_size=2`, `cpu_threads=6` dari preset
   "rendah") tercatat apa adanya di `settings_json` attempt, dan opsi ekspor
   "Markdown per transkrip" benar-benar menghasilkan berkas.

**Temuan baru di luar blueprint awal** (ditemukan saat menulis test):
- **P0-7** — counter `discovered` hasil scan hilang tergantung urutan nama file; lihat §3.7.
- **P1-5** — `cpu_threads_override = None` ditulis ke TOML sebagai `""`, sehingga
  `resolved_threads()` melempar `TypeError` pada pemanggil pertamanya. Bug ini tidak
  pernah terlihat justru **karena** setting-nya mati — persis kelas masalah yang diaudit.
  Diperbaiki di `to_document`/`_section_from_table` + toleransi config lama.

**Hasil ukur P1-2** (benchmark 5.000 file, 205 MB): prepare turun dari 2,49 dtk (rehash
semua) menjadi **0,16 dtk tanpa hashing sama sekali** — 16× lebih cepat, dan itu masih
meremehkan karena fixture ada di cache OS; arsip 13 ribu VN asli di HDD sebelumnya
disk-bound berhitungan menit. Ekstrapolasi 13.000 file: **±0,41 dtk**.

---

# 0. CARA CODING AGENT MEMAKAI DOKUMEN INI

1. Baca dokumen ini sampai habis sebelum mengedit kode. `PROJECT_BLUEPRINT.md` lama tetap berlaku KECUALI di titik yang secara eksplisit direvisi di sini (lihat §2).
2. Kerjakan per fase (§8). Setiap temuan punya ID (`P0-1`, `P1-3`, dst.) — gunakan ID itu di pesan commit.
3. Setiap perbaikan WAJIB disertai test regresi yang gagal sebelum fix dan lulus sesudahnya.
4. Jangan menjalankan transkripsi produksi ±13.000 file. Integration test maksimal 20 file audio nyata.
5. Jangan mengunggah audio/transkrip/nama ke layanan cloud mana pun. Unduhan model dari Hugging Face Hub tetap diizinkan (hanya bobot model yang diunduh).
6. Skema database hanya boleh berubah lewat file migrasi baru (`migrations/000N_*.sql`) yang aman dijalankan pada database berisi data lama.
7. UI tetap berbahasa Indonesia. Log boleh Inggris.
8. Setelah semua fase selesai: jalankan `scripts\test.ps1`, lalu build portable + installer, dan tunjukkan buktinya.

---

# 1. RINGKASAN EKSEKUTIF

Aplikasi ini fondasinya bagus (arsitektur berlapis, worker terpisah, no-repeat berbasis SHA-256, test lulus semua), tetapi ada **7 bug fungsional/UX yang membuatnya terasa rusak saat dipakai sungguhan**, dan **desain "batas aman 20 file" bertentangan langsung dengan tujuan produk: memproses ribuan file sekali jalan**. Selain itu banyak pengaturan yang sudah ada di config tetapi mati (tidak pernah dikonsumsi kode), dan tidak ada UI settings untuknya.

Prioritas:

| Kelas | Isi | Dampak |
|---|---|---|
| **P0** | Fungsi rusak: resume mematikan worker; refresh 750 ms merusak seleksi & input; statistik progres salah; batch langsung menimpa konfigurasi folder; FTS basi setelah proses ulang | Pengguna nyata akan menganggap aplikasi "tidak works" |
| **P1** | Skala ribuan file: hapus batas 20; hashing ulang tiap start; tanpa progres/ETA; model turbo + batched inference + cpu_threads | Target utama pemilik produk |
| **P2** | Settings lengkap + hidup; varian model & mode; UX polish; ekspor sesuai config | "Perfect, user-friendly, praktis" |

---

# 2. REVISI RESMI ATAS PROJECT_BLUEPRINT.md LAMA

Blueprint lama ditulis untuk fase *pembangunan* dan menanam "rem" agar agen tidak memproses arsip penuh. Rem itu sekarang salah tempat: ia tertanam di produk, bukan di proses build. Revisi resmi:

1. **DIHAPUS:** batas keras 20 file per batch pada produk (UI dan service). Diganti model *konfirmasi bertingkat* (§5.1). Batas 20 file TETAP berlaku untuk integration test agen.
2. **DIREVISI:** "Small default untuk 13.000 file pertama" → default tetap Small, tetapi katalog model diperluas dengan **Turbo (large-v3-turbo)** sebagai varian akurasi-tinggi-tetap-cepat (§6.1).
3. **DIREVISI:** "CPU int8, arsitektur boleh backend lain nanti" → tetap CPU default, tetapi `cpu_threads` dan batched inference WAJIB dipakai (§6.2). Backend GPU (whisper.cpp Vulkan untuk AMD) menjadi fase opsional terakhir, bukan v2 wajib.
4. **DIREVISI:** `task` config yang dipaksa `transcribe` → izinkan `translate` (Whisper hanya mendukung translate → Inggris) sebagai opsi eksplisit per-run (§6.3).
5. Semua aturan privasi, read-only source, no-repeat, dan resume-safety lama TETAP MENGIKAT.

---

# 3. TEMUAN P0 — FUNGSI RUSAK (WAJIB DIPERBAIKI DULU)

## P0-1 — Perintah *resume* mematikan worker

**Lokasi:** [worker/main.py:111-116](worker/main.py#L111-L116) + [worker/runtime.py:89-94](worker/runtime.py#L89-L94)

`WorkerLoop.run_one()` mengembalikan `False` setelah memproses perintah `resume` dan menyetel `paused=False`. Loop utama:

```python
did_work = worker.run_one()
if worker.stopped or (not did_work and not worker.paused):
    break
```

Setelah resume: `did_work=False`, `paused=False` → **break** → worker exit. Tombol **Lanjutkan** di UI (jalur `_start()` saat state `paused`) secara efektif menghentikan worker; antrean tersisa tidak diproses sampai pengguna menekan mulai lagi (yang memicu preflight baru).

**Masalah kedua di loop yang sama:** worker juga exit saat antrean kosong sesaat (`idle`) — padahal perintah `reprocess_selected` yang dikirim UI ke worker hidup butuh worker tetap hidup. Saat ini reprocess dari dialog detail hanya berfungsi kebetulan jika worker sedang sibuk.

**Fix yang diminta:**
- Ubah kontrak `run_one()` → kembalikan enum/status eksplisit: `PROCESSED | COMMAND_HANDLED | IDLE | PAUSED | STOPPED` (bukan bool).
- Loop utama: `STOPPED` → keluar; `PROCESSED`/`COMMAND_HANDLED` → lanjut tanpa tidur; `PAUSED` → tidur 1 dtk; `IDLE` → tidur 1 dtk dan **baru keluar setelah idle beruntun N detik (default 30) tanpa perintah baru**, tulis status `finished` ke status file sebelum exit.
- Test regresi: (a) enqueue `pause` lalu `resume` lalu satu file antrean → file tetap diproses oleh worker yang sama; (b) worker idle menerima `reprocess_selected` dalam jendela idle → file diproses.

## P0-2 — Timer refresh 750 ms merusak interaksi pengguna

**Lokasi:** [app/ui/launch.py:572-575](app/ui/launch.py#L572-L575) (`QTimer` → `self.refresh`), [launch.py:975-994](app/ui/launch.py#L975-L994) (`refresh`), [launch.py:1034-1055](app/ui/launch.py#L1034-L1055) (`_populate_table`)

Setiap 750 ms `refresh()`:
1. `_populate_table()` memanggil `clearSelection()` + `setRowCount()` → **seleksi baris pengguna di "Semua Transkrip" terhapus tiap 750 ms** → fitur *Hapus Riwayat Terpilih* praktis tidak bisa dipakai (ini fungsi rusak, bukan sekadar polish). Posisi scroll tabel juga ikut lompat.
2. `self.audio_root.setText(...)` dan `self.chat_root.setText(...)` ditulis ulang tiap tick → **pengguna tidak bisa mengetik path folder di Pengaturan** karena ketikan ditimpa.
3. Lima-plus query SQL (dua `COUNT(*)` + join FTS bila kolom cari terisi) berjalan tiap 750 ms — boros dan membuat UI tersendat pada database besar.
4. `textChanged` pada dua kolom pencarian memicu `refresh()` penuh **per keystroke** tanpa debounce.

**Fix yang diminta:**
- Pisahkan menjadi dua jalur: **tick ringan** (hanya baca `worker_status.json` + update progress bar/label, tiap 750 ms) dan **refresh data** (tabel, kartu metrik, settings) yang dipanggil hanya: saat pindah halaman navigasi, setelah operasi selesai, saat filter berubah, atau maksimal tiap 5 detik KETIKA worker aktif dan halaman yang relevan sedang terlihat.
- `_populate_table`: pertahankan seleksi (simpan set `audio_id` terpilih, pulihkan setelah repopulasi) dan pertahankan posisi scroll; jangan repopulasi jika data tidak berubah (bandingkan fingerprint ringan, mis. `MAX(updated_at)+COUNT(*)` per query).
- Kolom `audio_root`/`chat_root`: hanya diisi saat load halaman settings dan setelah simpan — tidak pernah dari tick. Tandai "kotor" saat user mengetik.
- Debounce pencarian 300 ms (pakai `QTimer.singleShot` reset-restart).
- Test: unit test logika preservasi seleksi; smoke test UI yang mengetik di kolom settings sementara timer berjalan.

## P0-3 — Statistik salah dan tidak konsisten ("statistik terlihat aneh")

**Lokasi:** [app/ui/launch.py:1124-1140](app/ui/launch.py#L1124-L1140), [worker/runtime.py:161-185](worker/runtime.py#L161-L185), [app/services/application_service.py:217-241](app/services/application_service.py#L217-L241)

Tiga akar masalah:

1. **Progress bar bohong.** `worker_status.json` berisi `queued` (sisa antrean) dan `completed` (**akumulasi sepanjang masa** dari seluruh DB dalam scope roots). UI menampilkan `completed/(queued+completed)` dengan label "% selesai pada sesi ini". Contoh nyata: 500 file selesai kemarin + 20 antrean baru → bar langsung ~96 % padahal sesi baru mulai.
2. **Kartu dashboard tidak menjumlah.** `Total VN` = semua state (termasuk `excluded` dan `no_speech`), tetapi kartu lain hanya `completed_preferred`, pending(4 state), review(`failed`+`missing_source`) → total ≠ jumlah kartu; pengguna melihat angka "hilang".
3. **Kartu "Perlu diperiksa" ≠ halaman Review.** Kartu menghitung `failed+missing_source`; halaman Review ([repositories.py:239-245](app/database/repositories.py#L239-L245)) menyaring `failed/missing_source/stale_source_changed` + match ambigu/unmatched + kualitas `Perlu Diperiksa/Gagal`. Angka kartu dan isi halaman tidak akan pernah cocok.

**Fix yang diminta:**
- **Status file v2** (naikkan `schema` ke 2), ditulis worker per file selesai: `session_started_at`, `session_total` (jumlah queued saat prepare selesai), `session_done`, `session_failed`, `current_file_basename`, `current_file_started_at`, `avg_seconds_per_file` (rata-rata bergulir), `eta_seconds` (=(session_total−session_done)×avg), plus counts lama. Progress bar = `session_done/session_total`; tampilkan juga `ETA ± X menit` dan nama file yang sedang diproses.
- **Definisi kartu dashboard formal** (tuliskan sebagai konstanta + docstring):
  - `Total VN` = seluruh baris dalam scope;
  - `Selesai` = `completed_preferred` + `verified`;
  - `Belum diproses` = `discovered` + `queued` + `processing` + `stale_source_changed`;
  - `Perlu ditinjau` = **persis kriteria `review_only` di repository** (satu sumber kebenaran: pindahkan kriteria itu ke satu fungsi/SQL view yang dipakai kartu DAN halaman Review);
  - Tambahkan baris kecil di bawah kartu: "Dikecualikan: N · Tanpa suara: N" sehingga penjumlahan selalu jelas.
- Test: hitung kartu vs total di fixture dengan semua state terwakili; verifikasi kartu review == total halaman review.

## P0-4 — "Pilih File Audio" menimpa konfigurasi folder audio

**Lokasi:** [app/services/application_service.py:156-159](app/services/application_service.py#L156-L159)

`add_audio_files()` MENGGANTI `config.paths.audio_roots` dengan folder induk file yang baru dipilih. Akibat: folder arsip yang dikonfigurasi pengguna hilang diam-diam; scope dashboard/queue berubah; "Scan File Baru" berikutnya memindai folder yang salah. Ini juga salah satu penyebab "statistik aneh" (Total VN tiba-tiba mengecil).

**Fix yang diminta:**
- Pisahkan konsep: `paths.audio_roots` (folder arsip, dikelola hanya dari Settings/wizard) vs `paths.direct_roots` (akumulasi folder batch langsung; field TOML baru, otomatis dedupe, bisa dibersihkan dari Settings).
- Scope efektif untuk dashboard/queue/worker = gabungan keduanya.
- Migrasi config: jika versi lama hanya punya `audio_roots` hasil timpaan, biarkan apa adanya (tidak bisa dipulihkan) tetapi jangan pernah menimpanya lagi.
- Test: `add_audio_files` tidak mengubah `audio_roots`; scan folder arsip tetap bekerja setelah batch langsung.

## P0-5 — Indeks pencarian (FTS) basi setelah proses ulang / koreksi manual

**Lokasi:** [app/database/worker_repository.py:267-275](app/database/worker_repository.py#L267-L275), [app/services/application_service.py:465-473](app/services/application_service.py#L465-L473), skema [migrations/0001_initial.sql:257-261](migrations/0001_initial.sql#L257-L261)

`transcript_fts` adalah FTS5 **contentless** (`content=''`). Pada tabel contentless, `INSERT OR REPLACE` **tidak menghapus indeks lama** (tidak ada penghapusan yang bisa dilakukan tanpa `contentless_delete=1`) — token transkrip lama tetap terindeks. Setelah pengguna memproses ulang file atau menyimpan koreksi manual, pencarian isi transkrip bisa mencocokkan teks lama yang sudah tidak ada. Perilaku persisnya tergantung versi SQLite; di beberapa versi operasi ini malah melempar error yang di worker akan menandai file `failed` padahal transkripsi sukses.

**Fix yang diminta (pilih satu, dokumentasikan):**
- **Opsi A (disarankan):** migrasi baru → buat ulang `transcript_fts` sebagai FTS5 contentless dengan `contentless_delete=1` (butuh SQLite ≥ 3.43 — verifikasi versi sqlite3 bawaan Python 3.12 di CI dan runtime PyInstaller), lalu `DELETE` baris lama sebelum `INSERT` baru di kedua call-site; rebuild penuh isi indeks di migrasi.
- **Opsi B:** ganti ke FTS5 *external content* atas view/tabel transkrip preferred + trigger sinkronisasi.
- Tambah test regresi: transkripsi → proses ulang dengan teks berbeda → cari kata dari teks lama HARUS tidak ketemu, kata baru HARUS ketemu; ulangi untuk koreksi manual.

## P0-6 — `verify(full_hash=False)` tidak memverifikasi apa pun tetapi menulis "verified"

**Lokasi:** [app/transcription/model_registry.py:123-141](app/transcription/model_registry.py#L123-L141)

Bukan bug fatal, tetapi jalur `set_default_model`/worker-start memanggil `verify(full_hash=False)` yang hanya cek keberadaan+ukuran file, sementara registry menyimpan `verification_state: "verified"` sejak instalasi. Jika file model korup di disk (ukuran sama), worker gagal dengan pesan generik. **Fix ringan:** saat worker start gagal memuat model (exception dari CTranslate2), tulis pesan status berbeda ("Model rusak — unduh ulang dari Pengaturan") dan tandai registry `verification_state: "suspect"`.

## P0-7 — Counter hasil scan hilang tergantung urutan nama file **(TEMUAN BARU)**

**Lokasi:** [app/services/discovery_service.py](app/services/discovery_service.py) — `_scan_one`

Ditemukan saat menulis test regresi P0-4. `_scan_one` menerima summary berjalan **dan** mengembalikan summary baru, tetapi tiap cabang membangun ulang `ScanSummary` dan hanya membawa sebagian field. Cabang `unchanged` mengembalikan `ScanSummary(unchanged=…, unreadable=…, zero_byte=…)` — **`discovered` jatuh ke 0**. Akibatnya pesan "Scan selesai: N file baru" salah setiap kali ada file tak berubah yang diproses setelah file baru (tergantung urutan alfabet). Ini penyebab lain dari keluhan "statistik terlihat aneh".

**Fix (sudah diterapkan):** `_scan_one` kini mengembalikan **delta** untuk satu file saja, dan kedua pemanggil (`scan_audio_root`, `scan_audio_files`) menjumlahkannya lewat `_combine_scan_summaries` yang memang sudah benar. Test: `test_scan_summary_keeps_discovered_count_when_an_unchanged_file_follows`.

---

# 4. TEMUAN P1 — SKALA "RIBUAN SEKALIGUS"

## P1-1 — Hapus batas keras 20 file; ganti konfirmasi bertingkat

**Lokasi:** [app/services/application_service.py:134-151](app/services/application_service.py#L134-L151) (`maximum_files=20`), [app/ui/launch.py:253-254](app/ui/launch.py#L253-L254) (`DISPLAY_LIMIT=250`, `SAFE_BATCH_LIMIT=20`), [launch.py:472-476](app/ui/launch.py#L472-L476), teks bantuan di banyak tempat.

Spesifikasi baru (§5.1 menjelaskan UX-nya):
- `add_audio_files`: tanpa batas keras. Parameter `maximum_files` dihapus atau dinaikkan menjadi rail-guard 50.000.
- Dialog preflight: tabel menjadi **paged/virtualized** (model/`QTableView` + `QAbstractTableModel`, bukan `QTableWidget` 13k baris), dengan "Centang semua (N file)" yang bekerja pada **query**, bukan pada baris yang terlihat.
- Aturan konfirmasi: ≤200 file → langsung; >200 file → checkbox konfirmasi (yang sudah ada); >2.000 file → tambah estimasi waktu kasar ("±X jam dengan model M pada komputer ini" — pakai `avg_seconds_per_file` historis dari attempt sebelumnya bila ada, atau tabel default konservatif) dan tombol mulai baru aktif setelah konfirmasi.
- `prepare_test_batch` (uji 20 file) TETAP ADA apa adanya — itu memang fitur uji.

## P1-2 — `QueueService.prepare()` menghash ulang SELURUH arsip di tiap start worker

**Lokasi:** [app/services/queue_service.py:72-74](app/services/queue_service.py#L72-L74)

`sha256_file()` dijalankan untuk setiap file dalam scope setiap kali worker mulai. Pada 13.000 VN (~puluhan GB di HDD) ini bisa berarti belasan menit "diam" sebelum file pertama diproses — pengguna akan mengira hang.

**Fix yang diminta:**
- Simpan `size_bytes` + `mtime` pada versi sumber (sudah ada di skema). Di `prepare()`: jika `size` dan `mtime` file di disk == yang tersimpan → **lewati hashing**, pakai `stored_sha256`. Hash ulang hanya jika berbeda (kemungkinan file berubah) — semantik no-repeat tetap aman karena identitas final tetap SHA-256.
- Bungkus seluruh `prepare()` dalam SATU transaksi (saat ini `_set_state` membuka transaksi immediate per file → 13k transaksi).
- Tulis progres prepare ke status file (`state: "preparing"`, `prepare_done/prepare_total`) supaya UI menampilkan "Menyiapkan antrean… 4.200/13.000".
- Target ukur: prepare 13k file yang tidak berubah < 5 detik (tanpa I/O hash).

## P1-3 — Engine tidak memakai lever performa yang sudah tersedia

**Lokasi:** [app/transcription/engine.py:46-51](app/transcription/engine.py#L46-L51), [app/config.py:60-68](app/config.py#L60-L68)

Riset (Juli 2026): faster-whisper mendukung `cpu_threads`/`num_workers` di `WhisperModel`, `BatchedInferencePipeline` (klaim resmi ~4× lebih cepat), dan model **large-v3-turbo** (decoder dipangkas 32→4 layer; benchmark komunitas int8 ±7× lebih cepat dari large-v3 dengan penurunan akurasi kecil; multibahasa, termasuk Indonesia). Referensi: repo [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper), model CT2 [deepdml/faster-whisper-large-v3-turbo-ct2](https://huggingface.co/deepdml/faster-whisper-large-v3-turbo-ct2), kartu model [openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo).

**Fix yang diminta:**
- `FasterWhisperEngine.load()`: teruskan `cpu_threads=cfg.transcription.resolved_threads()` dan `compute_type=cfg.transcription.compute_type` (dua setting yang saat ini mati).
- Tambah opsi `use_batched_inference: bool = true` di config → bungkus dengan `BatchedInferencePipeline(model)` dan `batch_size` konfigurabel (default 8; dokumentasikan trade-off RAM). Catat di `settings_json` attempt agar compat-key tetap jujur.
- Sanity-check: VN WhatsApp umumnya pendek (<2 menit); batched inference paling berdampak pada audio panjang — tetap bermanfaat + wajib untuk file panjang, buat fallback otomatis ke non-batched bila import gagal.
- Pin versi `faster-whisper` terbaru yang stabil di `requirements-lock.txt`; `engine_version` di `claim_next` jangan lagi hard-code `"1.1.1"` — baca dari `importlib.metadata`.

## P1-4 — Tidak ada progres granular & ETA (lihat P0-3 untuk status file v2)

Selain status file v2: scan folder ([app/services/discovery_service.py:75-111](app/services/discovery_service.py#L75-L111)) juga tanpa progres — untuk 13k file scan+hash pertama bisa >30 menit. Tambahkan callback progres (per 50 file) yang dipublikasikan ke UI (signal dari `ServiceJob` atau file status scan), tampilkan "Scan: 3.150 file ditemukan…" di `operation_label`.

---

# 5. SPESIFIKASI UX ("user-friendly, praktis")

## 5.1 Alur batch besar

1. Beranda → "Pilih File Audio" (tanpa batas) ATAU folder arsip di Settings → Scan.
2. "Siapkan & Mulai Transkripsi" → dialog preflight baru:
   - Ringkasan atas: "13.204 file belum selesai · perkiraan ±22 jam (Small) / ±9 jam (Turbo)".
   - Pilihan model (radio, dengan status terpasang + tombol "Unduh" inline per model — jangan paksa pengguna bolak-balik ke Settings).
   - Pilihan cakupan: `Semua file belum selesai` / `Hanya yang saya centang` (tabel paged) / `Hanya file gagal`.
   - Konfirmasi bertingkat sesuai P1-1.
3. Selama berjalan: bar sesi (P0-3), nama file aktif, kecepatan (file/menit), ETA, tombol Jeda/Berhenti Aman selalu terlihat.
4. Selesai: notifikasi ringkas + tombol "Buat Hasil" menonjol.

## 5.2 Settings lengkap (menghidupkan config yang mati)

**Lokasi masalah:** [app/config.py](app/config.py) memvalidasi banyak field yang tidak pernah dikonsumsi: `cpu_preset`, `cpu_threads_override`, `compute_type`, `review_model`, `retry_limit`, `ui.theme`, `ui.page_size`, `ui.poll_interval_ms`, seluruh `ExportConfig`. [app/ui/launch.py:907-973](app/ui/launch.py#L907-L973) hanya menampilkan folder/model/backup.

**Fix yang diminta — halaman Pengaturan & Data ditata ulang menjadi grup (pakai `QTabWidget` atau seksi ber-header):**
1. **Sumber Data:** folder arsip audio (multi-root: daftar + tambah/hapus, bukan satu QLineEdit), folder batch langsung (read-only + tombol bersihkan), folder ekspor chat, tombol scan.
2. **Transkripsi:** model default (dengan status terpasang/unduh/impor + progres unduhan — `snapshot_download` punya callback; saat ini unduhan 3,1 GB tampak beku tanpa progres), bahasa (`id`/`auto`), mode (`transcribe`/`translate→Inggris`), preset CPU (`rendah/seimbang/maksimal` → `resolved_threads()`), batched inference on/off + batch size, VAD on/off, beam size (advanced, collapsed).
3. **Ekspor:** checkbox per format (konsumsi `ExportConfig` di `ApplicationService.export_all` → teruskan ke `ExportService`; saat ini semua format selalu ditulis dan `include_individual/generated_at` tidak pernah bisa diubah).
4. **Tampilan:** tema (`system/light/dark` — implementasikan varian gelap `theme.py` ATAU hapus field-nya; jangan biarkan setting bohong), ukuran halaman tabel.
5. **Data & Diagnostik:** backup/pulihkan/diagnostik (yang sudah ada) + tombol "Buka Folder Data".

Aturan umum: **setiap setting yang tampil harus benar-benar berefek, dan setiap setting yang berefek harus tampil.** Field config yang diputuskan tidak diimplementasikan → hapus dari dataclass (dengan migrasi config yang mentolerir field lama).

## 5.3 Polish lain yang ditemukan audit

- [launch.py:1219](app/ui/launch.py#L1219): judul dialog file picker masih "maksimal 20" — sinkronkan semua copy dengan aturan baru (grep "20").
- Dialog detail: tombol "Proses Ulang dengan Model Default" sebaiknya menawarkan pilihan model (termasuk `review_model` — cara menghidupkan setting itu, atau hapus).
- `closeEvent` sudah benar (worker tak dibunuh) — pertahankan; tambahkan opsi ketiga "Biarkan worker jalan di latar belakang" yang menutup jendela tanpa stop (saat ini Yes=stop, No=batal tutup; tidak ada "tutup UI, biarkan worker").
- First-run wizard: halaman model masih menyebut unduh manual di Settings — setelah §5.2, tawarkan unduh Small langsung dari wizard (opsional, dengan konfirmasi ukuran).
- Pastikan `QMediaPlayer` mendukung `.opus` di mesin target (Windows 10 lama tanpa codec); jika tidak, fallback dekode PyAV → WAV sementara di folder temp aplikasi.

---

# 6. KATALOG MODEL & MODE (varian lebih lengkap)

## 6.1 Katalog model baru ([app/transcription/model_registry.py:26-48](app/transcription/model_registry.py#L26-L48))

| Key | Repo HF (CT2) | Ukuran ±unduh | Posisi |
|---|---|---|---|
| `small` | `Systran/faster-whisper-small` | ±480 MB | Default, tercepat |
| `medium` | `Systran/faster-whisper-medium` | ±1,5 GB | Akurasi menengah |
| `turbo` **(BARU)** | `deepdml/faster-whisper-large-v3-turbo-ct2` | ±1,6 GB | **Direkomendasikan untuk arsip besar: akurasi kelas large, kecepatan mendekati small** |
| `high` | `Systran/faster-whisper-large-v3` | ±3,1 GB | Akurasi maksimum, paling lambat |

Tugas: tambah entri `turbo` (verifikasi nama file bobot di repo tsb — pola `model.bin`/`vocabulary.*` sama), perbarui semua UI yang meng-hardcode tiga model (radio preflight, filter model di halaman Semua Transkrip, wizard, dokumen), dan migrasi registry yang mulus untuk instalasi lama.

## 6.2 Runtime

Lihat P1-3. GPU: **fase opsional terakhir** — jalur paling realistis untuk AMD di Windows adalah backend `whisper.cpp` build Vulkan sebagai engine kedua di balik `TranscriptionEngine` protocol (bukti komunitas ±8× realtime large model di RX 9070 XT; lihat [whisper.cpp Vulkan di Windows](https://github.com/jerryshell/whisper.cpp-windows-vulkan-bin) dan [tulisan integrasi Subtitle Edit](https://www.maroonmed.com/subtitle-edit-and-whisper-cpp-stt-on-amd-and-other-non-nvidia-gpus-with-vulkan/)). JANGAN kerjakan sebelum semua fase lain selesai dan stabil.

## 6.3 Mode translate

Opsi per-run `task=translate` (output Inggris) di preflight, disimpan di `settings_json` attempt (sudah ikut compat-key). Validasi config yang menolak `translate` ([app/config.py:76-77](app/config.py#L76-L77)) dihapus. UI harus jujur: "Terjemahan hanya tersedia ke bahasa Inggris (batasan Whisper)."

---

# 7. PERBANDINGAN DENGAN APLIKASI GRATIS YANG SUDAH ADA (hasil riset)

Pertanyaan pemilik: "apakah ada aplikasi terbaik yang gratis untuk ini?" Jawaban audit:

| Aplikasi | Gratis | Kekuatan | Kenapa TIDAK menggantikan app ini |
|---|---|---|---|
| **Buzz** (sudah ada installer-nya di folder ini) | Ya (MIT) | GUI Whisper matang, batch | Tidak ada: metadata pengirim/chat WhatsApp, no-repeat SHA-256, resume 13k file, ekspor second-brain per-tanggal |
| **Vibe** | Ya | GUI modern, GPU | Sama seperti di atas |
| **Subtitle Edit + whisper.cpp Vulkan** | Ya | GPU AMD kencang | Berorientasi subtitle video, bukan arsip VN + metadata chat |
| **WhisperX / faster-whisper CLI** | Ya | Paling cepat, diarization | Bukan untuk pengguna nontechnical |

**Keputusan:** lanjutkan aplikasi ini (nilai uniknya adalah *pipeline metadata WhatsApp + database riwayat + resume*), tetapi serap teknik dari mereka: model turbo, batched inference, progres/ETA ala Buzz.

---

# 8. FASE PENGERJAAN & DEFINITION OF DONE

**Fase 1 — P0 (fungsi rusak):** P0-1 … P0-6. DoD: test regresi baru lulus; skenario manual: mulai→jeda→lanjutkan→selesai pada 5 file berjalan mulus; seleksi tabel bertahan saat worker aktif; mengetik di settings tidak tertimpa; progress bar mulai dari 0 % pada sesi baru.

**Fase 2 — P1 (skala):** P1-1 … P1-4. DoD: prepare 13k-file sintetis (file dummy kecil, hash tersimpan) < 5 dtk; preflight menampilkan & mencentang >10k kandidat tanpa freeze (ukur < 2 dtk buka dialog); status file berisi ETA; batas 20 hilang dari seluruh copy UI.

**Fase 3 — P2 (settings, model, UX):** §5 + §6.1 + §6.3. DoD: setiap setting di UI terbukti berefek (test per setting); model `turbo` bisa diunduh-diverifikasi-dipakai; ekspor menghormati `ExportConfig`.

**Fase 4 — rilis:** perbarui `README.md`, `docs/USER_GUIDE.md`, catatan rilis; naikkan versi ke v0.3.0; build portable ZIP + installer via GitHub Actions; SHA256SUMS.
**Fase 5 (opsional, keputusan pemilik):** backend GPU whisper.cpp Vulkan (§6.2).

**Larangan tetap:** jangan mentranskripsi arsip produksi; jangan mengubah/memindahkan file sumber; jangan menambah telemetri; jangan menulis ulang modul yang tidak disebut dokumen ini tanpa alasan yang dicatat.

---

# 9. CATATAN VERIFIKASI AUDIT

- Test suite saat ini: `.venv\Scripts\python.exe -m pytest tests -q` → 147 lulus (2026-07-17). Bug di dokumen ini tidak tercakup test lama — itulah alasan setiap fix wajib membawa test baru.
- Bukti bug resume: [tests/unit/test_worker_runtime.py:297](tests/unit/test_worker_runtime.py#L297) hanya menguji `run_one()` level repository, tidak menguji kondisi break di `worker/main.py`.
- Semua nomor baris merujuk commit `e21fc31`.
