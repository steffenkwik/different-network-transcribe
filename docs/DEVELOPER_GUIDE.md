# Panduan Developer

Python 3.12 diperlukan. Pasang dependensi dengan `scripts/setup-dev.ps1`, lalu jalankan `scripts/test.ps1`.
Gunakan `scripts/build.ps1` untuk PyInstaller one-folder, Inno Setup per-user, portable ZIP, checksums, dan smoke
tests.

Arsitektur lima layer dan batas IPC terdapat di `COMPONENT_ARCHITECTURE.md` serta `WORKER_IPC_CONTRACT.md`.
UI tidak boleh memakai SQL/engine; worker tidak boleh mengimpor Qt; tests AST menegakkan aturan tersebut.

Jangan pernah menambahkan audio, chat export, database, backup, model, atau path data pengguna ke Git. Jalankan
`python scripts/scan_private_data.py` sebelum commit maupun release.
