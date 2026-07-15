"""PySide6 presentation layer: Indonesian navigation and first-run wizard only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from app import config as config_mod
from app.logging_setup import new_session_id, setup_logging
from app.paths import DataPaths, default_data_root
from app.resources import strings_id as S
from app.services.application_service import ApplicationService
from app.version import APP_NAME, APP_VERSION


class FirstRunWizard(QWizard):
    """Collects simple setup choices; services perform work after user confirmation."""

    def __init__(self, paths: DataPaths) -> None:
        super().__init__()
        self.paths = paths
        self.setWindowTitle(APP_NAME)
        self.addPage(self._welcome())
        self.addPage(self._data_location())
        self.addPage(self._source_folders())
        self.addPage(self._model())
        self.addPage(self._finish())

    def _welcome(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Selamat datang")
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(S.WIZARD_WELCOME))
        return page

    def _data_location(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Lokasi data")
        layout = QFormLayout(page)
        value = QLineEdit(str(self.paths.root))
        value.setReadOnly(True)
        layout.addRow("Folder data", value)
        return page

    def _source_folders(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Folder sumber")
        layout = QFormLayout(page)
        audio = QLineEdit()
        audio.setPlaceholderText("Pilih folder audio nanti di Pengaturan & Data")
        chat = QLineEdit()
        chat.setPlaceholderText("Pilih folder ekspor chat nanti di Pengaturan & Data")
        layout.addRow("Folder audio", audio)
        layout.addRow("Folder ekspor chat", chat)
        return page

    def _model(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Pilih model")
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(S.MODEL_SMALL_TITLE))
        layout.addWidget(QLabel(S.MODEL_MEDIUM_TITLE))
        return page

    def _finish(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Selesai")
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(S.WIZARD_FINISH))
        return page


class MainWindow(QMainWindow):
    def __init__(self, paths: DataPaths | None = None, service: ApplicationService | None = None) -> None:
        super().__init__()
        self.paths = paths
        self.service = service
        self.setWindowTitle(APP_NAME)
        self.resize(1180, 760)
        central = QWidget()
        root = QHBoxLayout(central)
        navigation = QVBoxLayout()
        self.pages = QStackedWidget()
        for index, label in enumerate((S.NAV_HOME, S.NAV_ALL, S.NAV_REVIEW, S.NAV_SETTINGS)):
            button = QPushButton(label)
            button.clicked.connect(lambda _, i=index: self.pages.setCurrentIndex(i))
            navigation.addWidget(button)
        navigation.addStretch(1)
        root.addLayout(navigation, 1)
        root.addWidget(self.pages, 5)
        self.pages.addWidget(self._home())
        self.pages.addWidget(self._all())
        self.pages.addWidget(self._review())
        self.pages.addWidget(self._settings())
        self.setCentralWidget(central)
        self._worker_status_timer = QTimer(self)
        self._worker_status_timer.setInterval(750)
        self._worker_status_timer.timeout.connect(self.refresh)
        self._worker_status_timer.start()

    def _home(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(f"{APP_NAME} {APP_VERSION}"))
        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)
        self.worker_label = QLabel("Worker tidak aktif")
        self.worker_progress = QProgressBar()
        self.worker_progress.setRange(0, 100)
        layout.addWidget(self.worker_label)
        layout.addWidget(self.worker_progress)
        self.scan_button = QPushButton(S.ACTION_SCAN)
        self.scan_button.clicked.connect(self._scan)
        layout.addWidget(self.scan_button)
        self.test_button = QPushButton(S.ACTION_TEST_20)
        self.test_button.setEnabled(False)
        self.test_button.setToolTip("Pilih batch uji setelah pengaturan worker tersedia.")
        layout.addWidget(self.test_button)
        self.start_button = QPushButton(S.ACTION_START)
        self.start_button.clicked.connect(self._start)
        layout.addWidget(self.start_button)
        self.pause_button = QPushButton(S.ACTION_PAUSE)
        self.pause_button.clicked.connect(self._pause)
        layout.addWidget(self.pause_button)
        self.stop_button = QPushButton(S.ACTION_SAFE_STOP)
        self.stop_button.clicked.connect(self._safe_stop)
        layout.addWidget(self.stop_button)
        self.export_button = QPushButton(S.ACTION_EXPORT)
        self.export_button.clicked.connect(self._export)
        layout.addWidget(self.export_button)
        layout.addWidget(QPushButton(S.ACTION_OPEN_OUTPUT))
        layout.addStretch(1)
        return page

    def _all(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(S.NAV_ALL))
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Status",
                "Pengirim",
                "Chat",
                S.LABEL_WHATSAPP_TIME,
                "Nama File",
                "Durasi",
                "Model",
                "Kualitas",
                "Terakhir Diproses",
            ]
        )
        layout.addWidget(self.table)
        return page

    def _review(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(S.NAV_REVIEW))
        layout.addWidget(QLabel("Catatan ambigu, gagal, dan perlu ditinjau akan muncul di sini."))
        layout.addStretch(1)
        return page

    def _settings(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(S.NAV_SETTINGS))
        layout.addWidget(QLabel(S.MODEL_CHANGE_NOTICE))
        self.audio_root = QLineEdit()
        self.audio_root.setPlaceholderText("Belum ada folder audio")
        choose = QPushButton("Pilih Folder Audio")
        choose.clicked.connect(self._choose_audio_root)
        save = QPushButton("Simpan Folder Audio")
        save.clicked.connect(self._save_audio_root)
        layout.addWidget(self.audio_root)
        layout.addWidget(choose)
        layout.addWidget(save)
        layout.addWidget(QPushButton("Unduh/Impor Model"))
        backup = QPushButton("Backup Sekarang")
        backup.clicked.connect(self._backup)
        layout.addWidget(backup)
        layout.addWidget(QPushButton("Pulihkan Paket"))
        layout.addStretch(1)
        return page

    def refresh(self) -> None:
        if self.service is None:
            self.summary_label.setText("Total VN: 0    Selesai: 0    Belum Diproses: 0")
            return
        counts = self.service.dashboard_counts()
        self.summary_label.setText(
            f"Total VN: {counts.total}    Selesai: {counts.completed}    "
            f"Belum Diproses: {counts.pending}    Perlu Diperiksa: {counts.review}    "
            f"Gagal: {counts.failed}"
        )
        page = self.service.transcript_page(limit=100)
        self.table.setRowCount(len(page.rows))
        for index, row in enumerate(page.rows):
            values = (
                row["current_state"], row["sender"] or S.UNKNOWN_SENDER, row["chat"] or "-",
                row["whatsapp_message_at"] or S.UNKNOWN_WHATSAPP_TIME, row["basename"],
                row["duration_seconds"] or "-", row["model_name"] or "-", row["quality_status"] or "-",
                row["last_processed_at"] or "-",
            )
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(str(value)))
        root = self.service.configured_audio_root()
        self.audio_root.setText("" if root is None else str(root))
        self._refresh_worker_status()

    def _refresh_worker_status(self) -> None:
        if self.paths is None or not self.paths.worker_status_file.is_file():
            self.worker_label.setText("Worker tidak aktif")
            self.worker_progress.setValue(0)
            return
        try:
            status = json.loads(self.paths.worker_status_file.read_text(encoding="utf-8"))
            counts = status.get("counts", {})
            queued = int(counts.get("queued", 0))
            completed = int(counts.get("completed", 0))
            total = queued + completed
            self.worker_label.setText(status.get("last_safe_message") or f"Worker: {status.get('state', 'tidak diketahui')}")
            self.worker_progress.setValue(0 if total == 0 else round(100 * completed / total))
        except (OSError, ValueError, TypeError):
            self.worker_label.setText("Status worker tidak dapat dibaca")

    def _require_service(self) -> ApplicationService | None:
        if self.service is None:
            QMessageBox.warning(self, APP_NAME, "Layanan aplikasi belum tersedia.")  # type: ignore[call-arg]
        return self.service

    def _show_error(self, exc: Exception) -> None:
        QMessageBox.warning(self, APP_NAME, str(exc))  # type: ignore[call-arg]

    def _scan(self) -> None:
        service = self._require_service()
        if service is None:
            return
        try:
            summary = service.scan_audio()
            self.refresh()
            QMessageBox.information(
                self, APP_NAME, f"Scan selesai: {summary.discovered} file baru, {summary.unchanged} tidak berubah."
            )
        except (OSError, ValueError) as exc:
            self._show_error(exc)

    def _export(self) -> None:
        service = self._require_service()
        if service is None:
            return
        try:
            count = service.export_all()
            QMessageBox.information(self, APP_NAME, f"Hasil dibuat untuk {count} transkrip.")
        except OSError as exc:
            self._show_error(exc)

    def _start(self) -> None:
        service = self._require_service()
        if service is None:
            return
        try:
            pid = service.start_transcription()
            self.worker_label.setText(f"Memulai worker (PID {pid})…")
            QTimer.singleShot(1000, self.refresh)
        except (RuntimeError, ValueError) as exc:
            self._show_error(exc)

    def _pause(self) -> None:
        service = self._require_service()
        if service is None:
            return
        try:
            service.pause_transcription()
            QMessageBox.information(self, APP_NAME, "Permintaan jeda dikirim.")
        except RuntimeError as exc:
            self._show_error(exc)

    def _safe_stop(self) -> None:
        service = self._require_service()
        if service is None:
            return
        try:
            service.safe_stop_transcription()
            QMessageBox.information(self, APP_NAME, "Permintaan berhenti aman dikirim.")
        except RuntimeError as exc:
            self._show_error(exc)

    def _choose_audio_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pilih Folder Audio")
        if folder:
            self.audio_root.setText(folder)

    def _save_audio_root(self) -> None:
        service = self._require_service()
        if service is None:
            return
        try:
            service.save_audio_root(Path(self.audio_root.text()))
            QMessageBox.information(self, APP_NAME, "Folder audio disimpan.")
        except ValueError as exc:
            self._show_error(exc)

    def _backup(self) -> None:
        service = self._require_service()
        if service is None:
            return
        try:
            package = service.create_backup()
            QMessageBox.information(self, APP_NAME, f"Backup dibuat: {package.name}")
        except OSError as exc:
            self._show_error(exc)


def run_ui(data_dir: Path | None = None, self_test: bool = False) -> int:
    paths = DataPaths(root=data_dir or default_data_root())
    paths.ensure()
    cfg = config_mod.load(paths.config_file, paths.config_lastgood_file)
    service = ApplicationService(paths)
    service.ensure_database()
    setup_logging(
        paths.logs_dir,
        session_id=new_session_id(),
        role="ui",
        level=cfg.diagnostics.log_level,
        allow_transcript_bodies=cfg.privacy.log_transcript_bodies,
        keep_days=cfg.diagnostics.keep_log_days,
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    window = MainWindow(paths, service)
    window.show()
    window.refresh()
    return _run_self_test(app, window) if self_test else app.exec()


def _run_self_test(app: QApplication, window: MainWindow) -> int:
    result: dict[str, object] = {}

    def check() -> None:
        result.update(
            visible=window.isVisible(),
            title=window.windowTitle(),
            platform=QApplication.platformName(),
        )
        app.quit()

    QTimer.singleShot(300, check)
    app.exec()
    ok = bool(result.get("visible")) and result.get("title") == APP_NAME
    print(
        f"SELF_TEST {'PASS' if ok else 'FAIL'} visible={result.get('visible')} title={result.get('title')!r} platform={result.get('platform')!r} version={APP_VERSION}"
    )
    return 0 if ok else 1
