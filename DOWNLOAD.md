# Unduh Different Network Transcribe

## Pilih versi aplikasi

| Pilihan | Untuk siapa | Unduh |
| --- | --- | --- |
| Installer Windows | Kebanyakan pengguna; membuat shortcut dan uninstaller. | [Unduh EXE installer](https://github.com/steffenkwik/different-network-transcribe/releases/download/v0.3.0/DifferentNetworkTranscribe-Setup-x64-v0.3.0.exe) |
| Portable Windows | Tidak ingin instalasi; jalankan langsung dari folder hasil ekstrak. | [Unduh ZIP portable](https://github.com/steffenkwik/different-network-transcribe/releases/download/v0.3.0/DifferentNetworkTranscribe-Portable-x64-v0.3.0.zip) |

Semua rilis resmi tersedia di [halaman GitHub Releases](https://github.com/steffenkwik/different-network-transcribe/releases).
Jangan gunakan **Code → Download ZIP** untuk memasang aplikasi: ZIP tersebut
berisi source code, bukan aplikasi EXE.

## Jalankan aplikasi

### Installer EXE

1. Klik **Unduh EXE installer** di atas.
2. Periksa SHA-256 sesuai bagian keamanan di bawah.
3. Jalankan `DifferentNetworkTranscribe-Setup-x64-v0.3.0.exe`.
4. Ikuti langkah instalasi lalu buka aplikasi dari Start Menu atau shortcut desktop.

### Portable ZIP

1. Klik **Unduh ZIP portable** di atas.
2. Periksa SHA-256 sesuai bagian keamanan di bawah.
3. Klik kanan ZIP, pilih **Extract All**, lalu buka folder hasil ekstrak.
4. Klik dua kali `DifferentNetworkTranscribe.exe`.

## Pemeriksaan keamanan sebelum menjalankan EXE

Setiap release menyediakan [SHA256SUMS.txt](https://github.com/steffenkwik/different-network-transcribe/releases/download/v0.3.0/SHA256SUMS.txt).
Checksum mendeteksi file yang rusak atau berubah saat unduhan. Ini **bukan**
pengganti pemeriksaan antivirus atau tanda tangan kode.

Cara termudah pada Windows:

1. Unduh `SHA256SUMS.txt` dari release yang sama dengan aplikasi.
2. Buka PowerShell pada folder Downloads.
3. Jalankan salah satu perintah berikut, lalu bandingkan hasilnya dengan nama
   berkas yang sama di `SHA256SUMS.txt`.

```powershell
Get-FileHash .\DifferentNetworkTranscribe-Setup-x64-v0.3.0.exe -Algorithm SHA256
Get-FileHash .\DifferentNetworkTranscribe-Portable-x64-v0.3.0.zip -Algorithm SHA256
```

Atau gunakan [VERIFIKASI_DOWNLOAD.ps1](VERIFIKASI_DOWNLOAD.ps1) dari repository
ini. Script tersebut membandingkan hash file dengan `SHA256SUMS.txt` yang Anda
unduh. Contoh:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\VERIFIKASI_DOWNLOAD.ps1 `
  -File "$HOME\Downloads\DifferentNetworkTranscribe-Setup-x64-v0.3.0.exe" `
  -Manifest "$HOME\Downloads\SHA256SUMS.txt"
```

Jika hasilnya **VALID**, file cocok dengan manifest. Jika **TIDAK VALID**,
jangan jalankan file; hapus dan unduh kembali dari halaman release resmi.
`-ExecutionPolicy Bypass` hanya berlaku untuk satu proses pemeriksaan ini;
pilih cara `Get-FileHash` di atas jika tidak ingin menjalankan script.

## Tentang SmartScreen dan antivirus

Installer belum memiliki code-signing certificate, sehingga SmartScreen dapat
menampilkan peringatan untuk file baru. Unduh hanya dari tautan release resmi,
periksa SHA-256, dan lakukan pemindaian antivirus jika diperlukan. Jangan
menonaktifkan proteksi Windows secara permanen untuk menjalankan aplikasi.
