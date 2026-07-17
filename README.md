# Different Network Transcribe

Desktop Windows app untuk mengindeks dan mentranskripsikan voice note WhatsApp
**secara lokal**. Audio, ekspor chat, dan transkrip tidak dikirim ke layanan
transkripsi cloud.

## Install dan mulai

1. Unduh installer terbaru dari [GitHub Releases](https://github.com/steffenkwik/different-network-transcribe/releases/latest), lalu jalankan file `DifferentNetworkTranscribe-Setup-x64-v*.exe`.
2. Atau ekstrak file `DifferentNetworkTranscribe-Portable-x64-v*.zip`, jalankan `DifferentNetworkTranscribe.exe`, dan pilih folder data yang dapat ditulis.
3. Di Beranda, klik **Pilih File Audio** atau tarik dan lepas hingga 20 file audio. Tidak perlu membuat folder khusus; file tetap di lokasi asal dan akan terlihat pada daftar persiapan sebelum diproses.
4. Atau, dari **Pengaturan & Data**, pilih folder audio serta folder ekspor chat jika ingin melakukan scan folder.
5. Unduh atau impor model lokal secara eksplisit, pilih model dan file pada dialog persiapan, lalu mulai transkripsi.

Shortcut desktop memakai logo resmi Different Network. Windows mungkin
menampilkan SmartScreen karena installer belum ditandatangani; verifikasi hash
di `SHA256SUMS.txt` sebelum menjalankannya.

## Model lokal

- **Small** — paling cepat dan direkomendasikan untuk test pertama.
- **Medium** — lebih akurat, lebih lambat.
- **High** — opsi lokal paling akurat, jauh lebih lambat, membutuhkan unduhan sekitar 3,1 GB dan RAM sekitar 5 GB.

Model tidak pernah diunduh otomatis. Pilih secara eksplisit dari **Pengaturan &
Data**. Audio dan transkrip tidak pernah diunggah ke API transkripsi cloud.

## Tambah file langsung dan ambil hasil

Untuk pekerjaan cepat, gunakan **Pilih File Audio** di Beranda atau tarik file ke area
drop. Aplikasi menerima maksimal 20 file per batch aman, menampilkan semuanya di
dialog **Siapkan Transkripsi**, dan memberi Anda pilihan model serta checkbox untuk
mengecualikan file sebelum worker dimulai. Tidak ada audio yang dipindahkan, disalin,
atau diubah.

Setelah **Buat Hasil** selesai, folder hasil dibuka otomatis dan lokasi lengkapnya
ditampilkan di aplikasi. Anda tetap dapat membukanya lagi dengan tombol **Buka Folder
Hasil**.

## Keamanan data

- File sumber hanya dibaca; aplikasi tidak mengubah, memindahkan, atau menghapus audio maupun ekspor chat.
- Identitas file memakai SHA-256. File pindah atau rename dengan byte yang sama tidak memicu transkripsi ulang.
- File selesai tidak diproses ulang karena mengganti model, pengaturan, atau format ekspor.
- Metadata ambigu tetap **Pengirim tidak diketahui**, bukan ditebak.

## Hapus riwayat terpilih

Di **Semua Transkrip**, pilih satu atau lebih baris dengan Ctrl atau Shift, lalu
klik **Hapus Riwayat Terpilih**. Konfirmasi menjelaskan apa yang dihapus.
Audio sumber, folder sumber, fingerprint file, dan metadata chat tidak pernah
dihapus. File yang dibersihkan tetap dikecualikan sampai Anda memilihnya kembali
untuk transkripsi baru.

## Developer quick start

```powershell
scripts\setup-dev.ps1
scripts\test.ps1
scripts\build.ps1
```

Lihat [panduan pengguna](docs/USER_GUIDE.md), [panduan developer](docs/DEVELOPER_GUIDE.md),
[catatan rilis](docs/RELEASE.md), dan [panduan test aman 20 file](docs/BEGINNER_20_FILE_TEST.md).
