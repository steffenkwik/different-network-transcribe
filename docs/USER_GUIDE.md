# Panduan Pengguna

## Folder sumber

Pilih folder audio dan folder export chat dari Pengaturan. Keduanya diperlakukan sebagai sumber **read-only**.
Timestamp WhatsApp berasal dari export chat; `File dibuat di Windows` dan `File diubah di Windows` adalah data
filesystem yang terpisah dan bukan pengganti timestamp WhatsApp.

## Model dan privasi

Small adalah pilihan awal yang disarankan. Medium lebih akurat namun lebih lambat. Model hanya diunduh ketika
Anda meminta; audio tidak pernah diunggah. Perubahan model default berlaku untuk file baru/pending, bukan file
yang sudah selesai.

## Proses dan hasil

Gunakan **Scan File Baru**, lalu **Mulai / Lanjutkan**. Jeda dan Berhenti Aman menyelesaikan atau melepas file
saat ini tanpa menghapus riwayat. Hasil Markdown, TXT, CSV, dan JSONL dapat dibuat ulang dari SQLite tanpa
transkripsi ulang.

## Review dan pemulihan

Ambiguity, file rusak, atau kualitas rendah perlu ditinjau. Pilih proses ulang hanya untuk file tertentu; hasil
lama tetap disimpan. Buat backup `.dntbackup` sebelum operasi besar dan pulihkan hanya dari paket tepercaya.
