# Test Aman Maksimal 20 Voice Note

Panduan ini memakai **salinan** tepat 20 file. Folder WhatsApp asli tidak boleh dipindahkan, diubah, atau diproses
langsung untuk pengujian awal.

## Sebelum mulai

1. Pastikan memakai installer atau portable ZIP terbaru.
2. Buat folder kosong, misalnya `D:\VN-Test-20`.
3. Buka folder voice note WhatsApp asli di File Explorer.
4. Pilih tepat 20 file `.opus`: tahan `Ctrl` sambil klik file yang berbeda, lalu tekan `Ctrl+C`.
5. Buka `D:\VN-Test-20`, tekan `Ctrl+V`. Ini membuat salinan; sumber asli tidak berubah.

## Menjalankan test

1. Buka **Different Network Transcribe**.
2. Klik **Pengaturan & Data**.
3. Klik **Pilih Folder Audio**, pilih `D:\VN-Test-20`, lalu klik **Simpan Folder Audio**.
4. Klik **Beranda** lalu **Scan File Baru**.
5. Pastikan kartu **Total VN** menampilkan `20`. Jika bukan 20, berhenti dan periksa folder test.
6. Klik **Mulai / Lanjutkan**. Status worker dan progress bar harus berubah dari *Memulai worker* menjadi
   *running*, lalu selesai/idle. Jangan tutup aplikasi saat proses berjalan.
7. Setelah selesai, klik **Buat Hasil**. Hasil ada di folder data aplikasi pada `Output`.

## Verifikasi no-repeat

1. Klik **Mulai / Lanjutkan** sekali lagi.
2. Tidak boleh ada transkripsi baru; status harus kembali idle dengan cepat.
3. Jika aplikasi meminta proses ulang, jangan setujui kecuali Anda memang memilih file tertentu untuk diulang.

## Jika ada masalah

- **Model tidak ditemukan atau rusak:** kembali ke Pengaturan dan impor/unduh model Small.
- **Worker langsung idle:** pastikan Total VN = 20 setelah scan dan file `.opus` dapat dibaca.
- **Progress tidak bergerak selama beberapa menit:** klik Berhenti Aman, tutup aplikasi, lalu kirim screenshot status
  worker dan halaman Beranda. Jangan menghapus database atau file sumber.
