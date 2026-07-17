# Panduan Instalasi dan Penggunaan

## Instalasi

Unduh installer atau portable ZIP dari halaman **Releases** repository ini.

Untuk installer, jalankan `DifferentNetworkTranscribe-Setup-x64-v*.exe` dan
ikuti langkah di layar. Untuk versi portable, ekstrak ZIP ke folder yang dapat
ditulis lalu jalankan `DifferentNetworkTranscribe.exe`.

Pada pembukaan pertama, pilih folder data. Jangan pilih folder instalasi yang
dilindungi Windows. Folder data menyimpan database, model lokal, hasil, backup,
dan log aplikasi.

## Menambahkan audio

Di halaman **Beranda**, gunakan **Pilih File Audio** atau tarik file audio ke
area drop. Anda juga dapat memilih folder audio pada **Pengaturan & Data**
untuk memindai arsip. File sumber tetap berada di lokasi asal.

Jika Anda mempunyai ekspor chat WhatsApp, tambahkan folder ekspor chat dari
**Pengaturan & Data**, scan, lalu jalankan pencocokan metadata agar waktu,
pengirim, dan chat dapat ditampilkan bila tersedia.

## Menjalankan transkripsi

Klik **Siapkan & Mulai Transkripsi**. Pilih model lokal dan cakupan file:

- **Semua file belum selesai** untuk memproses seluruh file yang tersedia.
- **Hanya file yang saya centang** untuk memilih rekaman tertentu.

Batch besar meminta konfirmasi. Anda dapat menjeda atau menghentikan dengan
aman; audio dan hasil yang sudah selesai tidak dihapus.

## Memeriksa dan membuat hasil

Saat worker selesai, aplikasi membuka preview hasil terbaru. Pilih baris untuk
melihat teks beserta waktu WhatsApp atau waktu selesai, durasi, pengirim/chat,
model, dan kualitas. Gunakan **Preview Transkripsi** untuk membukanya lagi.

Klik **Buat Hasil** untuk memilih nama dan format:

- Markdown (`.md`)
- Teks (`.txt`)
- CSV (`.csv`)
- JSONL (`.jsonl`)

Setiap ekspor dibuat di folder hasil spesifik. Jika nama tidak diisi, nama
folder audio aktif digunakan sebagai nama berkas. Tombol **Buka Hasil Terakhir**
membuka folder ekspor tersebut langsung di Windows Explorer.

## Privasi dan pemulihan

Audio dan teks tidak dikirim ke layanan transkripsi cloud. Untuk menjaga data,
buat backup dari **Pengaturan & Data** sebelum melakukan perubahan besar.
Gunakan **Hapus Riwayat Terpilih** hanya untuk menghapus data transkrip yang
diturunkan; file audio sumber tetap tidak diubah.
