# Different Network Transcribe

Aplikasi desktop Windows untuk mentranskripsikan voice note WhatsApp secara
lokal. Audio, ekspor chat, dan teks transkrip tetap berada di komputer Anda.

## Unduh dan instal

1. Buka halaman [GitHub Releases](https://github.com/steffenkwik/different-network-transcribe/releases/latest).
2. Pilih salah satu berkas berikut:
   - `DifferentNetworkTranscribe-Setup-x64-v*.exe` untuk instalasi biasa.
   - `DifferentNetworkTranscribe-Portable-x64-v*.zip` bila ingin menjalankan aplikasi tanpa instalasi.
3. Jalankan installer, atau ekstrak ZIP lalu jalankan `DifferentNetworkTranscribe.exe`.
4. Saat pertama kali dibuka, pilih folder data yang dapat ditulis. Database,
   model, hasil, log, dan backup tersimpan di folder ini.

Windows dapat menampilkan SmartScreen karena aplikasi belum ditandatangani.
Sebelum menjalankan berkas, cocokkan SHA-256 dengan `SHA256SUMS.txt` yang ada
di release yang sama.

## Cara pakai singkat

1. Pada **Beranda**, klik **Pilih File Audio** atau tarik file audio ke aplikasi.
   File sumber tidak disalin, dipindahkan, atau diubah.
2. Klik **Siapkan & Mulai Transkripsi**, pilih model dan file yang ingin diproses,
   lalu klik **Mulai Transkripsi**.
3. Setelah proses selesai, preview otomatis menampilkan teks, waktu, durasi,
   pengirim/chat, model, dan kualitas. Preview juga selalu dapat dibuka dari
   tombol **Preview Transkripsi**.
4. Klik **Buat Hasil**, beri nama hasil bila diperlukan, lalu pilih format
   Markdown, TXT, CSV, atau JSONL.
5. Hasil disimpan dalam folder bernama sama dengan nama yang dipilih. Jika
   nama dikosongkan, aplikasi memakai nama folder audio aktif. Gunakan tombol
   **Buka Hasil Terakhir** untuk langsung membuka folder yang tepat.

Panduan lengkap tersedia di [PANDUAN_INSTALL_DAN_PAKAI.md](PANDUAN_INSTALL_DAN_PAKAI.md).

## Model lokal

- **Small** — paling cepat dan disarankan untuk percobaan awal.
- **Medium** — lebih akurat, lebih lambat.
- **Turbo** — pilihan baik untuk arsip besar; unduhan sekitar 1,6 GB.
- **High** — paling akurat, paling lambat; unduhan sekitar 3,1 GB dan RAM lebih besar.

Model diunduh hanya ketika Anda memilihnya. Aplikasi tidak mengunggah audio
atau transkrip ke layanan transkripsi cloud.

## Keamanan data

- Audio dan ekspor chat diperlakukan sebagai sumber baca-saja.
- Transkrip selesai tidak diproses ulang hanya karena model atau format hasil berubah.
- Metadata yang ambigu ditandai untuk diperiksa, bukan ditebak.
- Backup dan hasil tersimpan pada folder data yang Anda pilih.

## Isi repository

Repository publik ini memuat source code aplikasi, aset, migrasi database,
konfigurasi installer, lisensi, serta panduan pengguna. Dokumen perencanaan,
audit internal, test, dan alat pengembangan tidak disertakan.
