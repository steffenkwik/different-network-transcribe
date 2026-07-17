"""Indonesian user-facing strings (blueprint: "The user sees Indonesian language;
logs may use English").

Keeping every visible string here means the "no forbidden label" rule is testable:
`test_no_tanggal_file_label` greps this module. Addendum section 14 forbids the
generic label `Tanggal File`, because a Windows file time is not a WhatsApp time.
"""

from __future__ import annotations

# --- Timestamp labels. These three must stay exactly distinct. ---------------
LABEL_WHATSAPP_TIME = "Timestamp WhatsApp"
LABEL_WINDOWS_CREATED = "File dibuat di Windows"
LABEL_WINDOWS_MODIFIED = "File diubah di Windows"
UNKNOWN_WHATSAPP_TIME = "Timestamp WhatsApp tidak diketahui"
UNKNOWN_SENDER = "Pengirim tidak diketahui"

# --- Navigation -------------------------------------------------------------
NAV_HOME = "Beranda"
NAV_ALL = "Semua Transkrip"
NAV_REVIEW = "Perlu Diperiksa"
NAV_SETTINGS = "Pengaturan dan Data"

# --- Primary actions --------------------------------------------------------
ACTION_SCAN = "Scan File Baru"
ACTION_TEST_20 = "Tes Maksimal 20 VN"
ACTION_START = "Mulai / Lanjutkan"
ACTION_PAUSE = "Jeda"
ACTION_SAFE_STOP = "Berhenti Aman"
ACTION_EXPORT = "Buat Hasil"
ACTION_OPEN_OUTPUT = "Buka Folder Hasil"

# --- Summary cards ----------------------------------------------------------
CARD_TOTAL = "Total VN"
CARD_DONE = "Selesai"
CARD_PENDING = "Belum Diproses"
CARD_REVIEW = "Perlu Diperiksa"
CARD_FAILED = "Gagal"
CARD_UNKNOWN_SENDER = "Pengirim Tidak Diketahui"

# --- Wizard -----------------------------------------------------------------
WIZARD_WELCOME = (
    "Different Network Transcribe memproses audio secara lokal di komputer ini.\n"
    "Audio dan transkrip tidak dikirim ke cloud."
)
WIZARD_FINISH = "Different Network Transcribe siap digunakan."
MODEL_SMALL_TITLE = "Small — Cepat, direkomendasikan"
MODEL_MEDIUM_TITLE = "Medium — Lebih akurat, lebih lambat"
MODEL_TURBO_TITLE = "Turbo — Akurat dan tetap cepat"
MODEL_HIGH_TITLE = "High — Paling akurat, paling lambat"

# --- Safety messages --------------------------------------------------------
WORKER_ALREADY_RUNNING = "Proses transkripsi sudah berjalan."
MODEL_CHANGE_NOTICE = (
    "Model baru hanya digunakan untuk file yang belum selesai. "
    "File yang sudah selesai tidak akan diulang kecuali Anda memilihnya secara manual."
)
DEFAULT_MODEL_CHANGE_SHORT = "Mengubah model default tidak akan mengulang file yang sudah selesai."
CLOSING_WHILE_ACTIVE = "Transkripsi masih berlangsung."
CLOSING_STOP_AND_CLOSE = "Berhenti Aman dan Tutup"
CLOSING_CANCEL = "Batalkan"
FILE_UNREADABLE = "File tidak dapat dibaca. File dilewati dan proses dilanjutkan."
MODEL_MISSING = "Model tidak ditemukan atau rusak."

# --- Quality categories (blueprint section 14) ------------------------------
QUALITY_GOOD = "Baik"
QUALITY_FAIR = "Cukup"
QUALITY_REVIEW = "Perlu Diperiksa"
QUALITY_NO_SPEECH = "Tidak Ada Suara"
QUALITY_FAILED = "Gagal"
QUALITY_METADATA_UNCLEAR = "Metadata Tidak Jelas"
QUALITY_SOURCE_CHANGED = "Sumber Berubah"
