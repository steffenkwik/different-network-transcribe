# Release Checklist

1. `scripts/test.ps1` lulus dan private-data scan lulus.
2. `scripts/build.ps1` menghasilkan installer dan portable ZIP berversi, serta `SHA256SUMS.txt`.
3. `scripts/smoke-test.ps1 -Artifact All` lulus.
4. Bila akan menerbitkan model offline, jalankan
   `python scripts/build_model_packs.py --models-dir <folder-Models-aplikasi>` secara eksplisit.
   Pastikan model packs dan data pribadi bukan bagian dari Git maupun installer.
5. Uji upgrade yang mempertahankan folder data sebelum publikasi.

Model Small/Medium/High didistribusikan terpisah sebagai release asset. Jangan unggah source audio atau database.
