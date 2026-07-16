# Panduan Pengguna

## Folder sumber

Pilih folder audio dan folder export chat dari **Pengaturan & Data**. Keduanya diperlakukan sebagai sumber **read-only**.
Timestamp WhatsApp berasal dari export chat; `File dibuat di Windows` dan `File diubah di Windows` adalah data
filesystem yang terpisah dan bukan pengganti timestamp WhatsApp.

Untuk pengujian awal, pilih **Tes Maksimal 20 VN** di Beranda dan arahkan ke folder salinan berisi 1–20 file.
Aplikasi menolak folder yang berisi lebih dari 20 audio pada alur ini. Setelah scan chat, klik **Cocokkan Metadata**;
metadata yang ambigu tetap masuk ke **Perlu Diperiksa**, bukan ditebak.

## Model dan privasi

Small adalah pilihan awal yang disarankan. Medium lebih akurat namun lebih lambat. Model hanya diunduh ketika
Anda meminta; audio tidak pernah diunggah. Perubahan model default berlaku untuk file baru/pending, bukan file
yang sudah selesai.

## Proses dan hasil

Gunakan **Scan File Baru**, lalu **Mulai / Lanjutkan**. Jeda dan Berhenti Aman menyelesaikan atau melepas file
saat ini tanpa menghapus riwayat. Daftar **Semua Transkrip** memakai pencarian nama file, filter status, dan
pagination; teks transkrip baru dimuat jika sebuah baris dibuka. Hasil Markdown, TXT, CSV, dan JSONL dapat dibuat
ulang dari SQLite tanpa transkripsi ulang.

## Review dan pemulihan

Ambiguity, file rusak, atau kualitas rendah perlu ditinjau. Buka baris untuk menyimpan koreksi metadata atau
versi transkrip manual; parser dan transkrip mesin asli tetap tersimpan. Pilih proses ulang hanya untuk file
tertentu; hasil lama tetap disimpan. Buat backup `.dntbackup` sebelum operasi besar dan pulihkan hanya dari paket
tepercaya—aplikasi membuat backup database saat ini sebelum menukar hasil pemulihan yang sudah divalidasi.
