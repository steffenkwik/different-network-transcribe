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

1. Buka **Different Network Transcribe** dan pilih **Beranda**.
2. Klik **Tes Maksimal 20 VN**.
3. Pilih folder `D:\VN-Test-20` yang tadi dibuat. Aplikasi menghitung isi folder dulu.
   - Bila isi folder 1–20 audio, aplikasi menjadikannya folder aktif dan memulai scan.
   - Bila lebih dari 20 audio, aplikasi menolak folder itu. Tidak ada file sumber yang diubah;
     kembali ke langkah persiapan dan buat folder salinan yang lebih kecil.
4. Tunggu pesan **Folder uji aman aktif**. Pastikan kartu **Total VN** menampilkan jumlah yang sama dengan
   folder uji (pada contoh ini `20`). Kartu hanya menghitung folder audio aktif; scan lama dari folder lain
   tidak ikut diproses.
5. Klik **Mulai / Lanjutkan**. Status worker dan progress bar harus berubah dari *Memulai worker* menjadi
   *running*, lalu selesai/idle. Jangan tutup aplikasi saat proses berjalan.
6. Setelah selesai, klik **Buat Hasil**, lalu klik **Buka Folder Hasil**. Windows Explorer akan membuka
   folder hasil yang aman untuk dibaca. Jangan mencari hasil di folder sumber audio.

## Verifikasi no-repeat

1. Klik **Mulai / Lanjutkan** sekali lagi.
2. Tidak boleh ada transkripsi baru; status harus kembali idle dengan cepat.
3. Jika aplikasi meminta proses ulang, jangan setujui kecuali Anda memang memilih file tertentu untuk diulang.

## Jika ada masalah

- **Model tidak ditemukan atau rusak:** buka **Pengaturan & Data**, lalu gunakan **Unduh Model** atau
  **Impor Model ZIP**. Pilih `small` bila ragu. Download hanya mengambil bobot model ke komputer ini;
  audio dan chat export tidak dikirim.
- **Worker langsung idle:** pastikan Total VN = 20 setelah scan dan file `.opus` dapat dibaca.
- **Progress tidak bergerak selama beberapa menit:** klik Berhenti Aman, tutup aplikasi, lalu kirim screenshot status
  worker dan halaman Beranda. Jangan menghapus database atau file sumber.
