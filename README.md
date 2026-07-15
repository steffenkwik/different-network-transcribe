# Different Network Transcribe

Desktop Windows app untuk mengindeks dan mentranskripsikan voice note WhatsApp **secara lokal**.
Audio, ekspor chat, dan transkrip tidak dikirim ke layanan transkripsi cloud.

## Safety promises

- File sumber hanya dibaca; aplikasi tidak mengubah, memindahkan, atau menghapus audio/chat export.
- Identitas file memakai SHA-256. Pindah atau rename dengan byte yang sama tidak memicu transkripsi ulang.
- File selesai tidak diproses ulang karena mengganti model, pengaturan, atau format export. Proses ulang hanya
  terjadi bila pengguna memilih file secara eksplisit atau bytes sumber berubah.
- Metadata pengirim hanya dipakai bila filename memberi bukti yang cukup; nilai ambigu tetap **Pengirim tidak diketahui**.
- Model Faster-Whisper dijalankan lokal pada CPU `int8`; model tidak masuk Git atau installer standar.

## Install dan mulai

1. Jalankan `DifferentNetworkTranscribe-Setup-x64.exe`, atau ekstrak `DifferentNetworkTranscribe-Portable-x64.zip`.
2. Pilih folder data yang dapat ditulis. Jangan gunakan folder aplikasi untuk data pribadi.
3. Dari **Pengaturan & Data**, pilih dan simpan folder audio serta folder export chat.
4. Unduh atau impor model Small secara eksplisit, lalu lakukan scan.
5. Periksa metadata yang ambigu sebelum memakai hasil export.

Windows mungkin menampilkan SmartScreen karena installer v1 belum ditandatangani. Verifikasi hash di
`SHA256SUMS.txt` sebelum menjalankannya.

## Developer quick start

```powershell
scripts\setup-dev.ps1
scripts\test.ps1
scripts\build.ps1
```

Lihat [panduan pengguna](docs/USER_GUIDE.md), [panduan developer](docs/DEVELOPER_GUIDE.md), dan
[catatan rilis](docs/RELEASE.md). Untuk pengujian awal, ikuti
[panduan test aman 20 file](docs/BEGINNER_20_FILE_TEST.md).
