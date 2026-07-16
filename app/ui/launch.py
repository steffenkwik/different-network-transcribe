"""PySide6 presentation layer for the local desktop workflow.

This module intentionally only renders views and invokes ApplicationService use
cases.  It contains no SQL and never imports the transcription engine.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
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
from app.services.application_service import ApplicationService, TestBatchSummary
from app.services.chat_import_service import ChatScanSummary
from app.services.discovery_service import ScanSummary
from app.services.metadata_matching_service import MatchingSummary
from app.ui.brand import DifferentNetworkMark
from app.ui.theme import APP_STYLESHEET
from app.version import APP_NAME, APP_VERSION


class ServiceJob(QThread):
    """Run an I/O-heavy application use case outside the Qt event thread."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, operation: Callable[[], object], parent: QWidget) -> None:
        super().__init__(parent)
        self._operation = operation

    def run(self) -> None:
        try:
            self.succeeded.emit(self._operation())
        except Exception as exc:  # The UI receives a safe service-level message only.
            self.failed.emit(str(exc) or "Operasi tidak dapat diselesaikan.")


class FirstRunWizard(QWizard):
    """Collect safe first-run choices before the normal four-section window opens."""

    def __init__(self, paths: DataPaths) -> None:
        super().__init__()
        self.paths = paths
        self.data_folder = QLineEdit(str(paths.root))
        self.audio_folder = QLineEdit()
        self.chat_folder = QLineEdit()
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
        choose = QPushButton("Pilih Lokasi Data")
        choose.clicked.connect(self._choose_data_folder)
        layout.addRow("Folder data", self.data_folder)
        layout.addRow("", choose)
        layout.addRow("", QLabel("Database, model, hasil, log, dan backup tersimpan di lokasi ini; bukan di Program Files."))
        return page

    def _source_folders(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Folder sumber")
        layout = QVBoxLayout(page)
        audio_choose = QPushButton("Pilih Folder Audio (opsional)")
        audio_choose.clicked.connect(self._choose_audio_folder)
        chat_choose = QPushButton("Pilih Folder Ekspor Chat (opsional)")
        chat_choose.clicked.connect(self._choose_chat_folder)
        layout.addWidget(self.audio_folder)
        layout.addWidget(audio_choose)
        layout.addWidget(self.chat_folder)
        layout.addWidget(chat_choose)
        layout.addWidget(
            QLabel(
                "Pilih folder audio dan ekspor chat di Pengaturan & Data. "
                "Untuk uji pertama, gunakan salinan maksimal 20 audio."
            )
        )
        return page

    def _choose_data_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Pilih Lokasi Data Aplikasi", self.data_folder.text())
        if selected:
            self.data_folder.setText(selected)

    def _choose_audio_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Pilih Folder Audio", self.audio_folder.text())
        if selected:
            self.audio_folder.setText(selected)

    def _choose_chat_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Pilih Folder Ekspor Chat", self.chat_folder.text())
        if selected:
            self.chat_folder.setText(selected)

    def selected_data_root(self) -> Path:
        candidate = Path(self.data_folder.text()).expanduser()
        if not candidate.name:
            raise ValueError("Pilih folder data yang valid.")
        return candidate

    def selected_audio_root(self) -> Path | None:
        return Path(self.audio_folder.text()).expanduser() if self.audio_folder.text().strip() else None

    def selected_chat_root(self) -> Path | None:
        return Path(self.chat_folder.text()).expanduser() if self.chat_folder.text().strip() else None

    def _model(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Model untuk transkripsi")
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Anda selalu memilih model lagi sebelum menekan Mulai."))
        layout.addWidget(QLabel(f"• {S.MODEL_SMALL_TITLE} — paling tepat untuk uji awal."))
        layout.addWidget(QLabel(f"• {S.MODEL_MEDIUM_TITLE} — untuk pemeriksaan yang lebih teliti."))
        layout.addWidget(QLabel("Unduh atau impor model secara eksplisit dari Pengaturan & Data. Audio tidak pernah dikirim ke cloud."))
        return page

    def _finish(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Selesai")
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(S.WIZARD_FINISH))
        return page


class TranscriptionSetupDialog(QDialog):
    """A deliberate, beginner-friendly preflight before the worker can start.

    A user chooses the local model and either selects a safe batch (the default)
    or makes an unmistakable opt-in to every incomplete file in the current root.
    The list is bounded so a 13,000-file archive never freezes Qt.
    """

    DISPLAY_LIMIT = 250
    SAFE_BATCH_LIMIT = 20

    def __init__(self, service: ApplicationService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self._candidate_ids: list[int] = []
        self._updating = False
        self.setWindowTitle("Siapkan Transkripsi")
        self.resize(900, 690)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        eyebrow = QLabel("LANGKAH TERAKHIR SEBELUM WORKER DIMULAI")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)
        heading = QLabel("Pilih model dan file yang akan diproses")
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        helper = QLabel(
            "Pilihan ini hanya memengaruhi file belum selesai. Transkrip yang sudah selesai tidak akan diulang kecuali Anda meminta proses ulang dari detail file."
        )
        helper.setObjectName("helperText")
        helper.setWordWrap(True)
        layout.addWidget(helper)

        self.model_status = self.service.model_status()
        model_section = QFrame()
        model_section.setObjectName("workflowCard")
        model_layout = QHBoxLayout(model_section)
        model_layout.setContentsMargins(16, 14, 16, 14)
        model_copy = QVBoxLayout()
        title = QLabel("1. Model lokal")
        title.setObjectName("sectionTitle")
        model_copy.addWidget(title)
        model_copy.addWidget(QLabel("Model dimuat sekali oleh worker dan tetap berada di komputer ini."))
        model_layout.addLayout(model_copy, 1)
        self.small_model = self._model_radio("small", S.MODEL_SMALL_TITLE, "Cepat; direkomendasikan untuk mulai.")
        self.medium_model = self._model_radio("medium", S.MODEL_MEDIUM_TITLE, "Lebih akurat; membutuhkan waktu lebih lama.")
        self.model_group = QButtonGroup(self)
        self.model_group.addButton(self.small_model)
        self.model_group.addButton(self.medium_model)
        model_layout.addWidget(self.small_model)
        model_layout.addWidget(self.medium_model)
        layout.addWidget(model_section)

        files_heading = QHBoxLayout()
        files_title = QLabel("2. Pilih file")
        files_title.setObjectName("sectionTitle")
        files_heading.addWidget(files_title)
        files_heading.addStretch(1)
        self.selection_count_label = QLabel()
        self.selection_count_label.setObjectName("statusPill")
        files_heading.addWidget(self.selection_count_label)
        layout.addLayout(files_heading)

        self.process_all = QCheckBox("Saya ingin mengaktifkan semua file belum selesai di folder ini")
        self.process_all.setToolTip(
            "Opsi ini menyalakan seluruh file belum selesai. Konfirmasi tambahan diperlukan agar koleksi besar tidak terproses tanpa sengaja."
        )
        self.process_all.toggled.connect(self._toggle_all_mode)
        layout.addWidget(self.process_all)
        self.confirm_all = QCheckBox("Saya memahami bahwa ini dapat memproses batch besar dan memakan waktu lama.")
        self.confirm_all.setVisible(False)
        self.confirm_all.toggled.connect(self._update_start_state)
        layout.addWidget(self.confirm_all)

        table_actions = QHBoxLayout()
        self.select_visible_button = QPushButton("Centang semua yang terlihat")
        self.select_visible_button.clicked.connect(lambda: self._check_visible(True))
        self.clear_visible_button = QPushButton("Kosongkan pilihan")
        self.clear_visible_button.clicked.connect(lambda: self._check_visible(False))
        table_actions.addWidget(self.select_visible_button)
        table_actions.addWidget(self.clear_visible_button)
        table_actions.addStretch(1)
        self.file_help = QLabel()
        self.file_help.setObjectName("subtle")
        table_actions.addWidget(self.file_help)
        layout.addLayout(table_actions)

        self.file_table = QTableWidget(0, 5)
        self.file_table.setHorizontalHeaderLabels(["Proses", "Nama file", "Durasi", "Status", "Lokasi relatif"])
        self.file_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.file_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.file_table.itemChanged.connect(self._selection_changed)
        header = self.file_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.file_table, 1)

        self.validation_label = QLabel()
        self.validation_label.setObjectName("helperText")
        self.validation_label.setWordWrap(True)
        layout.addWidget(self.validation_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.start_button = QPushButton("Mulai Transkripsi")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self._commit_and_accept)
        buttons.addButton(self.start_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_models()
        self._load_candidates()

    def _model_radio(self, key: str, title: str, description: str) -> QRadioButton:
        models = self.model_status.get("models", {})
        entry = models.get(key, {}) if isinstance(models, dict) else {}
        installed = bool(entry.get("installed")) if isinstance(entry, dict) else False
        label = f"{title}\n{description}\n{'Terpasang' if installed else 'Belum terpasang'}"
        radio = QRadioButton(label)
        radio.setProperty("modelKey", key)
        radio.setEnabled(installed)
        radio.setToolTip("Model belum terpasang. Buka Pengaturan & Data untuk unduh atau impor." if not installed else title)
        return radio

    def _load_models(self) -> None:
        default = str(self.model_status.get("default_model", "small"))
        preferred = self.small_model if default == "small" else self.medium_model
        other = self.medium_model if preferred is self.small_model else self.small_model
        if preferred.isEnabled():
            preferred.setChecked(True)
        elif other.isEnabled():
            other.setChecked(True)
        self.model_group.buttonClicked.connect(self._update_start_state)

    def _load_candidates(self) -> None:
        page = self.service.transcription_candidates(limit=self.DISPLAY_LIMIT)
        self._candidate_total = page.total
        self._updating = True
        self.file_table.setRowCount(len(page.rows))
        selected_by_default = 0
        for index, row in enumerate(page.rows):
            audio_id = int(row["id"])
            self._candidate_ids.append(audio_id)
            check = QTableWidgetItem()
            check.setData(Qt.ItemDataRole.UserRole, audio_id)
            currently_enabled = bool(row["transcription_enabled"])
            # A safe initial view selects at most 20 files; current selection is
            # respected only within that same safe cap.
            selected = currently_enabled and selected_by_default < self.SAFE_BATCH_LIMIT
            if selected:
                selected_by_default += 1
            check.setCheckState(Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked)
            self.file_table.setItem(index, 0, check)
            self.file_table.setItem(index, 1, QTableWidgetItem(str(row["basename"])))
            duration = row["duration_seconds"]
            duration_text = "-" if duration is None else f"{float(duration):.1f} dtk"
            self.file_table.setItem(index, 2, QTableWidgetItem(duration_text))
            self.file_table.setItem(index, 3, QTableWidgetItem(str(row["current_state"])))
            self.file_table.setItem(index, 4, QTableWidgetItem(str(row["current_relative_path"])))
        self._updating = False
        if page.total == 0:
            self.file_help.setText("Belum ada file siap diproses. Lakukan Scan File Baru terlebih dahulu.")
        elif page.total > self.DISPLAY_LIMIT:
            self.file_help.setText(f"Menampilkan {self.DISPLAY_LIMIT} dari {page.total} file; mode aman hanya memilih maks. 20.")
        else:
            self.file_help.setText(f"{page.total} file belum selesai ditemukan. Mode aman: maks. {self.SAFE_BATCH_LIMIT} file.")
        self._update_start_state()

    def _checked_ids(self) -> list[int]:
        ids: list[int] = []
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                value = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(value, int):
                    ids.append(value)
        return ids

    def _check_visible(self, checked: bool) -> None:
        self._updating = True
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item is not None:
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._updating = False
        self._update_start_state()

    def _selection_changed(self, _: QTableWidgetItem) -> None:
        if not self._updating:
            self._update_start_state()

    def _toggle_all_mode(self, checked: bool) -> None:
        self.file_table.setEnabled(not checked)
        self.select_visible_button.setEnabled(not checked)
        self.clear_visible_button.setEnabled(not checked)
        self.confirm_all.setVisible(checked and self._candidate_total > self.SAFE_BATCH_LIMIT)
        if not checked:
            self.confirm_all.setChecked(False)
        self._update_start_state()

    def _update_start_state(self, *_: object) -> None:
        selected = len(self._checked_ids())
        installed_model = self.model_group.checkedButton() is not None
        if self.process_all.isChecked():
            allowed = self._candidate_total > 0 and installed_model and (
                self._candidate_total <= self.SAFE_BATCH_LIMIT or self.confirm_all.isChecked()
            )
            message = (
                f"Seluruh {self._candidate_total} file belum selesai akan diaktifkan."
                if allowed
                else "Centang konfirmasi untuk menjalankan batch besar."
            )
        else:
            allowed = 0 < selected <= self.SAFE_BATCH_LIMIT and installed_model
            message = (
                f"{selected} file akan diproses dalam batch aman."
                if selected <= self.SAFE_BATCH_LIMIT
                else f"Pilih maksimal {self.SAFE_BATCH_LIMIT} file untuk batch aman, atau gunakan opsi semua file dengan konfirmasi."
            )
        if not installed_model:
            message = "Pasang Small atau Medium terlebih dahulu di Pengaturan & Data."
        self.selection_count_label.setText("Semua file" if self.process_all.isChecked() else f"{selected} dipilih")
        self.validation_label.setText(message)
        self.start_button.setEnabled(allowed)

    def _commit_and_accept(self) -> None:
        button = self.model_group.checkedButton()
        if button is None:
            return
        key = str(button.property("modelKey"))
        try:
            self.service.set_default_model(key)
            if self.process_all.isChecked():
                self.service.set_all_transcription_enabled(enabled=True)
            else:
                self.service.replace_transcription_selection(self._checked_ids())
        except (RuntimeError, ValueError) as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))  # type: ignore[call-arg]
            return
        self.accept()


class MainWindow(QMainWindow):
    PAGE_SIZE = 100

    def __init__(self, paths: DataPaths | None = None, service: ApplicationService | None = None) -> None:
        super().__init__()
        self.paths = paths
        self.service = service
        self._jobs: set[ServiceJob] = set()
        self._page_offset = 0
        self._review_offset = 0
        self._audio_output = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)
        self.setMinimumSize(1030, 660)
        central = QWidget()
        central.setObjectName("contentArea")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(250)
        navigation = QVBoxLayout(sidebar)
        navigation.setContentsMargins(18, 22, 18, 18)
        navigation.setSpacing(8)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        brand_row.addWidget(DifferentNetworkMark(sidebar, size=44))
        brand_text = QVBoxLayout()
        brand_name = QLabel("different network")
        brand_name.setObjectName("brandName")
        brand_product = QLabel("TRANSCRIBE")
        brand_product.setObjectName("brandProduct")
        brand_text.addWidget(brand_name)
        brand_text.addWidget(brand_product)
        brand_row.addLayout(brand_text)
        brand_row.addStretch(1)
        navigation.addLayout(brand_row)
        navigation.addSpacing(24)
        nav_label = QLabel("WORKSPACE")
        nav_label.setObjectName("eyebrow")
        navigation.addWidget(nav_label)
        self.pages = QStackedWidget()
        self.pages.currentChanged.connect(self._sync_navigation)
        self._nav_buttons: list[QPushButton] = []
        for index, label in enumerate((S.NAV_HOME, S.NAV_ALL, S.NAV_REVIEW, S.NAV_SETTINGS)):
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setAccessibleName(f"Buka halaman {label}")
            button.clicked.connect(lambda _, i=index: self.pages.setCurrentIndex(i))
            navigation.addWidget(button)
            self._nav_buttons.append(button)
        navigation.addStretch(1)
        self.local_only_label = QLabel("Lokal saja · tidak ada unggahan")
        self.local_only_label.setObjectName("statusPill")
        self.local_only_label.setWordWrap(True)
        navigation.addWidget(self.local_only_label)
        version_label = QLabel(f"v{APP_VERSION}")
        version_label.setObjectName("subtle")
        navigation.addWidget(version_label)
        root.addWidget(sidebar)
        root.addWidget(self.pages, 1)
        self.pages.addWidget(self._home())
        self.pages.addWidget(self._all())
        self.pages.addWidget(self._review())
        self.pages.addWidget(self._settings())
        self.setCentralWidget(central)
        self._sync_navigation(0)
        self._worker_status_timer = QTimer(self)
        self._worker_status_timer.setInterval(750)
        self._worker_status_timer.timeout.connect(self.refresh)
        self._worker_status_timer.start()

    def _sync_navigation(self, current_index: int) -> None:
        """Keep the selected sidebar destination obvious for mouse and keyboard users."""
        for index, button in enumerate(self._nav_buttons):
            button.setChecked(index == current_index)

    def _home(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(16)
        header = QHBoxLayout()
        title_group = QVBoxLayout()
        eyebrow = QLabel("TRANSKRIPSI LOKAL")
        eyebrow.setObjectName("eyebrow")
        title_group.addWidget(eyebrow)
        title = QLabel("Beranda")
        title.setObjectName("pageTitle")
        title_group.addWidget(title)
        subtitle = QLabel("Kelola transkripsi WhatsApp dengan aman, bertahap, dan sepenuhnya di komputer ini.")
        subtitle.setObjectName("helperText")
        title_group.addWidget(subtitle)
        header.addLayout(title_group)
        header.addStretch(1)
        self.operation_label = QLabel("Siap untuk langkah berikutnya.")
        self.operation_label.setObjectName("statusPill")
        header.addWidget(self.operation_label)
        layout.addLayout(header)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)
        self.metric_total = self._metric_card("Total VN", "0")
        self.metric_done = self._metric_card("Selesai", "0", accent=True)
        self.metric_pending = self._metric_card("Belum diproses", "0")
        self.metric_review = self._metric_card("Perlu diperiksa", "0")
        metrics.addWidget(self.metric_total, 0, 0)
        metrics.addWidget(self.metric_done, 0, 1)
        metrics.addWidget(self.metric_pending, 0, 2)
        metrics.addWidget(self.metric_review, 0, 3)
        layout.addLayout(metrics)

        workflow = QFrame()
        workflow.setObjectName("heroCard")
        workflow_layout = QHBoxLayout(workflow)
        workflow_layout.setContentsMargins(20, 18, 20, 18)
        workflow_copy = QVBoxLayout()
        workflow_title = QLabel("Siapkan transkripsi dengan tenang")
        workflow_title.setObjectName("sectionTitle")
        workflow_copy.addWidget(workflow_title)
        workflow_info = QLabel(
            "Pilih model, centang file yang memang ingin diproses, lalu mulai worker. "
            "File yang tidak dicentang disimpan sebagai dikecualikan dan tidak akan ikut antrean."
        )
        workflow_info.setObjectName("helperText")
        workflow_info.setWordWrap(True)
        workflow_copy.addWidget(workflow_info)
        workflow_layout.addLayout(workflow_copy, 1)
        self.start_button = QPushButton("Siapkan && Mulai Transkripsi")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setToolTip("Pilih model lokal dan file sebelum worker dimulai.")
        self.start_button.clicked.connect(self._start)
        workflow_layout.addWidget(self.start_button)
        layout.addWidget(workflow)

        progress_card = QFrame()
        progress_card.setObjectName("card")
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(18, 16, 18, 16)
        progress_title = QLabel("Status worker")
        progress_title.setObjectName("sectionTitle")
        progress_layout.addWidget(progress_title)
        self.worker_label = QLabel("Worker tidak aktif")
        self.worker_label.setObjectName("helperText")
        self.worker_progress = QProgressBar()
        self.worker_progress.setRange(0, 100)
        self.worker_progress.setFormat("%p% selesai pada sesi ini")
        progress_layout.addWidget(self.worker_label)
        progress_layout.addWidget(self.worker_progress)
        worker_actions = QHBoxLayout()
        self.scan_button = QPushButton(S.ACTION_SCAN)
        self.scan_button.clicked.connect(self._scan)
        worker_actions.addWidget(self.scan_button)
        self.test_button = QPushButton(S.ACTION_TEST_20)
        self.test_button.setToolTip("Pilih folder salinan berisi 1 sampai 20 audio untuk uji aman.")
        self.test_button.clicked.connect(self._prepare_test_batch)
        worker_actions.addWidget(self.test_button)
        self.pause_button = QPushButton(S.ACTION_PAUSE)
        self.pause_button.clicked.connect(self._pause)
        worker_actions.addWidget(self.pause_button)
        self.stop_button = QPushButton(S.ACTION_SAFE_STOP)
        self.stop_button.setObjectName("warningButton")
        self.stop_button.clicked.connect(self._safe_stop)
        worker_actions.addWidget(self.stop_button)
        self.retry_failed_button = QPushButton("Coba Lagi File Gagal")
        self.retry_failed_button.setToolTip("Hanya mengantrekan ulang file berstatus Gagal; file selesai tidak disentuh.")
        self.retry_failed_button.clicked.connect(self._retry_failed)
        worker_actions.addWidget(self.retry_failed_button)
        worker_actions.addStretch(1)
        progress_layout.addLayout(worker_actions)
        layout.addWidget(progress_card)

        output_card = QFrame()
        output_card.setObjectName("workflowCard")
        output_layout = QHBoxLayout(output_card)
        output_layout.setContentsMargins(18, 14, 18, 14)
        output_copy = QVBoxLayout()
        output_title = QLabel("Hasil dan pemulihan")
        output_title.setObjectName("sectionTitle")
        output_copy.addWidget(output_title)
        output_info = QLabel("Buat Markdown, TXT, CSV, dan JSONL dari database lokal kapan saja. Pembuatan hasil tidak mentranskripsi ulang audio.")
        output_info.setObjectName("helperText")
        output_info.setWordWrap(True)
        output_copy.addWidget(output_info)
        output_layout.addLayout(output_copy, 1)
        self.export_button = QPushButton(S.ACTION_EXPORT)
        self.export_button.clicked.connect(self._export)
        output_layout.addWidget(self.export_button)
        self.open_output_button = QPushButton(S.ACTION_OPEN_OUTPUT)
        self.open_output_button.clicked.connect(self._open_output)
        output_layout.addWidget(self.open_output_button)
        layout.addWidget(output_card)
        layout.addStretch(1)
        return page

    @staticmethod
    def _metric_card(label: str, value: str, *, accent: bool = False) -> QFrame:
        card = QFrame()
        card.setObjectName("metricCard")
        card.setMinimumHeight(92)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        value_label = QLabel(value)
        value_label.setObjectName("accentMetric" if accent else "metricValue")
        value_label.setProperty("metricRole", label)
        label_widget = QLabel(label)
        label_widget.setObjectName("metricLabel")
        card_layout.addWidget(value_label)
        card_layout.addWidget(label_widget)
        return card

    @staticmethod
    def _set_metric(card: QFrame, value: int) -> None:
        labels = cast(list[QLabel], list(card.findChildren(QLabel)))
        for label in labels:
            if label.property("metricRole") is not None:
                label.setText(str(value))
                return

    def _all(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(14)
        eyebrow = QLabel("ARSIP LOKAL")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel(S.NAV_ALL)
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        intro = QLabel("Cari dan buka detail hanya saat diperlukan. Daftar ini dimuat per halaman agar tetap cepat untuk koleksi besar.")
        intro.setObjectName("helperText")
        layout.addWidget(intro)
        controls = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cari nama file, pengirim, atau chat")
        self.search_input.textChanged.connect(self._reset_paging)
        self.transcript_search_input = QLineEdit()
        self.transcript_search_input.setPlaceholderText("Cari isi transkrip")
        self.transcript_search_input.textChanged.connect(self._reset_paging)
        self.state_filter = QComboBox()
        self.state_filter.addItem("Semua status", None)
        for label, value in (
            ("Selesai", "completed_preferred"),
            ("Antrean", "queued"),
            ("Ditemukan", "discovered"),
            ("Dikecualikan", "excluded"),
            ("Gagal", "failed"),
            ("Sumber berubah", "stale_source_changed"),
            ("Sumber hilang", "missing_source"),
        ):
            self.state_filter.addItem(label, value)
        self.state_filter.currentIndexChanged.connect(self._reset_paging)
        self.quality_filter = QComboBox()
        self.quality_filter.addItem("Semua kualitas", None)
        for label in ("Baik", "Perlu Diperiksa", "Tidak Ada Suara"):
            self.quality_filter.addItem(label, label)
        self.quality_filter.currentIndexChanged.connect(self._reset_paging)
        self.model_filter = QComboBox()
        self.model_filter.addItem("Semua model", None)
        self.model_filter.addItem("Small", "small")
        self.model_filter.addItem("Medium", "medium")
        self.model_filter.currentIndexChanged.connect(self._reset_paging)
        self.match_filter = QComboBox()
        self.match_filter.addItem("Semua metadata", None)
        for label in ("exact_unique", "exact_ambiguous", "unmatched", "filename_not_present"):
            self.match_filter.addItem(label, label)
        self.match_filter.currentIndexChanged.connect(self._reset_paging)
        self.date_filter = QLineEdit()
        self.date_filter.setPlaceholderText("Tanggal WA YYYY-MM-DD")
        self.date_filter.textChanged.connect(self._reset_paging)
        self.sort_filter = QComboBox()
        self.sort_filter.addItem("WA: lama ke baru", "whatsapp_asc")
        self.sort_filter.addItem("WA: baru ke lama", "whatsapp_desc")
        self.sort_filter.addItem("Nama file A-Z", "filename")
        self.sort_filter.addItem("Terakhir diproses", "processed_desc")
        self.sort_filter.currentIndexChanged.connect(self._reset_paging)
        controls.addWidget(self.search_input)
        controls.addWidget(self.transcript_search_input)
        controls.addWidget(self.state_filter)
        controls.addWidget(self.quality_filter)
        controls.addWidget(self.model_filter)
        controls.addWidget(self.match_filter)
        controls.addWidget(self.date_filter)
        controls.addWidget(self.sort_filter)
        layout.addLayout(controls)
        self.table = self._new_transcript_table()
        self.table.itemDoubleClicked.connect(self._open_detail_from_item)
        layout.addWidget(self.table)
        pagination = QHBoxLayout()
        self.previous_page_button = QPushButton("Sebelumnya")
        self.previous_page_button.clicked.connect(self._previous_page)
        self.next_page_button = QPushButton("Berikutnya")
        self.next_page_button.clicked.connect(self._next_page)
        self.page_label = QLabel()
        pagination.addWidget(self.previous_page_button)
        pagination.addWidget(self.next_page_button)
        pagination.addWidget(self.page_label)
        pagination.addStretch(1)
        layout.addLayout(pagination)
        return page

    def _review(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(14)
        eyebrow = QLabel("PERLU TINDAK LANJUT")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel(S.NAV_REVIEW)
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        review_intro = QLabel("Baris di bawah memerlukan perhatian: metadata ambigu/tidak cocok, sumber bermasalah, atau kualitas rendah.")
        review_intro.setObjectName("helperText")
        layout.addWidget(review_intro)
        self.review_table = self._new_transcript_table()
        self.review_table.itemDoubleClicked.connect(self._open_detail_from_item)
        layout.addWidget(self.review_table)
        controls = QHBoxLayout()
        self.review_previous_button = QPushButton("Sebelumnya")
        self.review_previous_button.clicked.connect(self._previous_review_page)
        self.review_next_button = QPushButton("Berikutnya")
        self.review_next_button.clicked.connect(self._next_review_page)
        self.review_page_label = QLabel()
        controls.addWidget(self.review_previous_button)
        controls.addWidget(self.review_next_button)
        controls.addWidget(self.review_page_label)
        controls.addStretch(1)
        layout.addLayout(controls)
        return page

    @staticmethod
    def _new_transcript_table() -> QTableWidget:
        table = QTableWidget(0, 9)
        table.setHorizontalHeaderLabels(
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
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        return table

    def _settings(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(10)
        eyebrow = QLabel("KONFIGURASI LOKAL")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel(S.NAV_SETTINGS)
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        model_notice = QLabel(S.MODEL_CHANGE_NOTICE)
        model_notice.setObjectName("helperText")
        model_notice.setWordWrap(True)
        layout.addWidget(model_notice)

        layout.addWidget(QLabel("Folder audio"))
        self.audio_root = QLineEdit()
        self.audio_root.setPlaceholderText("Belum ada folder audio")
        choose_audio = QPushButton("Pilih Folder Audio")
        choose_audio.clicked.connect(self._choose_audio_root)
        save_audio = QPushButton("Simpan Folder Audio")
        save_audio.clicked.connect(self._save_audio_root)
        layout.addWidget(self.audio_root)
        layout.addWidget(choose_audio)
        layout.addWidget(save_audio)

        layout.addWidget(QLabel("Folder ekspor chat WhatsApp"))
        self.chat_root = QLineEdit()
        self.chat_root.setPlaceholderText("Opsional: folder berisi ekspor chat .txt")
        choose_chat = QPushButton("Pilih Folder Ekspor Chat")
        choose_chat.clicked.connect(self._choose_chat_root)
        save_chat = QPushButton("Simpan Folder Ekspor Chat")
        save_chat.clicked.connect(self._save_chat_root)
        scan_chat = QPushButton("Scan Ekspor Chat")
        scan_chat.clicked.connect(self._scan_chats)
        match = QPushButton("Cocokkan Metadata")
        match.clicked.connect(self._match_metadata)
        layout.addWidget(self.chat_root)
        layout.addWidget(choose_chat)
        layout.addWidget(save_chat)
        layout.addWidget(scan_chat)
        layout.addWidget(match)

        self.model_status_label = QLabel("Status model belum dibaca.")
        choose_default = QPushButton("Pilih Model Default")
        choose_default.clicked.connect(self._choose_default_model)
        download_model = QPushButton("Unduh Model")
        download_model.clicked.connect(self._download_model)
        import_model = QPushButton("Impor Model ZIP")
        import_model.clicked.connect(self._import_model)
        layout.addWidget(self.model_status_label)
        layout.addWidget(choose_default)
        layout.addWidget(download_model)
        layout.addWidget(import_model)

        backup = QPushButton("Backup Sekarang")
        backup.clicked.connect(self._backup)
        restore = QPushButton("Pulihkan Paket")
        restore.clicked.connect(self._restore)
        diagnostics = QPushButton("Buat Paket Diagnostik Aman")
        diagnostics.clicked.connect(self._diagnostics)
        layout.addWidget(backup)
        layout.addWidget(restore)
        layout.addWidget(diagnostics)
        layout.addStretch(1)
        return page

    def refresh(self) -> None:
        if self.service is None:
            self._set_metric(self.metric_total, 0)
            self._set_metric(self.metric_done, 0)
            self._set_metric(self.metric_pending, 0)
            self._set_metric(self.metric_review, 0)
            return
        counts = self.service.dashboard_counts()
        self._set_metric(self.metric_total, counts.total)
        self._set_metric(self.metric_done, counts.completed)
        self._set_metric(self.metric_pending, counts.pending)
        self._set_metric(self.metric_review, counts.review)
        self._refresh_transcript_table()
        self._refresh_review_table()
        audio_root = self.service.configured_audio_root()
        chat_root = self.service.configured_chat_root()
        self.audio_root.setText("" if audio_root is None else str(audio_root))
        self.chat_root.setText("" if chat_root is None else str(chat_root))
        self._refresh_model_status()
        self._refresh_worker_status()

    def _refresh_transcript_table(self) -> None:
        if self.service is None:
            return
        state = self.state_filter.currentData()
        page = self.service.transcript_page(
            limit=self.PAGE_SIZE,
            offset=self._page_offset,
            state=None if state is None else str(state),
            metadata_query=self.search_input.text(),
            transcript_query=self.transcript_search_input.text(),
            quality_status=self.quality_filter.currentData(),
            model_name=self.model_filter.currentData(),
            match_status=self.match_filter.currentData(),
            whatsapp_date=self.date_filter.text().strip() or None,
            sort=str(self.sort_filter.currentData()),
        )
        self._populate_table(self.table, page.rows)
        self._set_page_controls(
            total=page.total,
            offset=self._page_offset,
            label=self.page_label,
            previous=self.previous_page_button,
            next_button=self.next_page_button,
        )

    def _refresh_review_table(self) -> None:
        if self.service is None:
            return
        page = self.service.review_page(limit=self.PAGE_SIZE, offset=self._review_offset)
        self._populate_table(self.review_table, page.rows)
        self._set_page_controls(
            total=page.total,
            offset=self._review_offset,
            label=self.review_page_label,
            previous=self.review_previous_button,
            next_button=self.review_next_button,
        )

    def _populate_table(self, table: QTableWidget, rows: list[Any]) -> None:
        table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (
                row["current_state"],
                row["sender"] or S.UNKNOWN_SENDER,
                row["chat"] or "-",
                row["whatsapp_message_at"] or S.UNKNOWN_WHATSAPP_TIME,
                row["basename"],
                row["duration_seconds"] or "-",
                row["model_name"] or "-",
                row["quality_status"] or "-",
                row["last_processed_at"] or "-",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                table.setItem(index, column, item)

    @staticmethod
    def _set_page_controls(
        *, total: int, offset: int, label: QLabel, previous: QPushButton, next_button: QPushButton
    ) -> None:
        first = 0 if total == 0 else offset + 1
        last = min(total, offset + MainWindow.PAGE_SIZE)
        label.setText(f"Menampilkan {first}-{last} dari {total}")
        previous.setEnabled(offset > 0)
        next_button.setEnabled(offset + MainWindow.PAGE_SIZE < total)

    def _refresh_model_status(self) -> None:
        if self.service is None:
            return
        status = self.service.model_status()
        raw_models = status["models"]
        models = raw_models if isinstance(raw_models, dict) else {}
        installed = [
            key
            for key, value in models.items()
            if isinstance(value, dict) and bool(value.get("installed"))
        ]
        available = ", ".join(installed) if installed else "belum ada"
        self.model_status_label.setText(
            f"Model default: {status['default_model']}. Terpasang: {available}."
        )

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
            self.worker_label.setText(
                status.get("last_safe_message") or f"Worker: {status.get('state', 'tidak diketahui')}"
            )
            self.worker_progress.setValue(0 if total == 0 else round(100 * completed / total))
        except (OSError, ValueError, TypeError):
            self.worker_label.setText("Status worker tidak dapat dibaca")

    def _run_background(
        self,
        label: str,
        operation: Callable[[], object],
        succeeded: Callable[[object], None],
    ) -> None:
        self.operation_label.setText(label)
        job = ServiceJob(operation, self)
        self._jobs.add(job)

        def on_success(result: object) -> None:
            succeeded(result)
            self.operation_label.setText("Siap.")
            self.refresh()

        def on_failure(message: str) -> None:
            self.operation_label.setText("Operasi gagal.")
            self._show_error(RuntimeError(message))

        job.succeeded.connect(on_success)
        job.failed.connect(on_failure)
        job.finished.connect(lambda: self._jobs.discard(job))
        job.start()

    def _require_service(self) -> ApplicationService | None:
        if self.service is None:
            QMessageBox.warning(self, APP_NAME, "Layanan aplikasi belum tersedia.")  # type: ignore[call-arg]
        return self.service

    def _show_error(self, exc: Exception) -> None:
        QMessageBox.warning(self, APP_NAME, str(exc))  # type: ignore[call-arg]

    def _show_info(self, message: str) -> None:
        QMessageBox.information(self, APP_NAME, message)

    def closeEvent(self, event: Any) -> None:
        """Never kill a local worker just because its window is closed."""
        if self.service is None or self.service.transcription_state() is None:
            event.accept()
            return
        choice = QMessageBox.question(
            self,
            APP_NAME,
            S.CLOSING_WHILE_ACTIVE,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice == QMessageBox.StandardButton.Yes:
            try:
                self.service.safe_stop_transcription()
            except RuntimeError as exc:
                self._show_error(exc)
                event.ignore()
                return
            event.accept()
            return
        event.ignore()

    def _scan(self) -> None:
        service = self._require_service()
        if service is None:
            return

        def complete(result: object) -> None:
            summary = result
            if not isinstance(summary, ScanSummary):
                return
            self._show_info(
                f"Scan selesai: {summary.discovered} file baru, {summary.unchanged} tidak berubah."
            )

        self._run_background("Memindai folder audio…", service.scan_audio, complete)

    def _prepare_test_batch(self) -> None:
        service = self._require_service()
        if service is None:
            return
        folder = QFileDialog.getExistingDirectory(self, "Pilih Folder Uji (maksimal 20 audio)")
        if not folder:
            return

        def complete(result: object) -> None:
            summary = result
            if not isinstance(summary, TestBatchSummary):
                return
            self._show_info(
                f"Folder uji aman aktif: {summary.source_count} audio. "
                f"Scan menemukan {summary.scan.discovered} file baru. "
                "Periksa Total VN, lalu klik Mulai / Lanjutkan."
            )

        self._run_background(
            "Menyiapkan batch uji maksimal 20 audio…",
            lambda: service.prepare_test_batch(Path(folder)),
            complete,
        )

    def _export(self) -> None:
        service = self._require_service()
        if service is None:
            return
        self._run_background(
            "Membuat hasil dari database lokal…",
            service.export_all,
            lambda result: self._show_info(f"Hasil dibuat untuk {result} transkrip."),
        )

    def _open_output(self) -> None:
        """Open only the app-owned derived-output directory in Windows Explorer."""
        if self.paths is None:
            QMessageBox.warning(self, APP_NAME, "Folder hasil belum tersedia.")  # type: ignore[call-arg]
            return
        self.paths.output_dir.mkdir(parents=True, exist_ok=True)
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.output_dir)))
        if not opened:
            QMessageBox.warning(self, APP_NAME, "Folder hasil tidak dapat dibuka.")  # type: ignore[call-arg]

    def _start(self) -> None:
        service = self._require_service()
        if service is None:
            return
        try:
            if service.transcription_state() == "paused":
                service.resume_transcription()
                self.worker_label.setText("Melanjutkan worker…")
            else:
                preflight = TranscriptionSetupDialog(service, self)
                if preflight.exec() != QDialog.DialogCode.Accepted:
                    return
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
            self._show_info("Permintaan jeda dikirim.")
        except RuntimeError as exc:
            self._show_error(exc)

    def _safe_stop(self) -> None:
        service = self._require_service()
        if service is None:
            return
        try:
            service.safe_stop_transcription()
            self._show_info("Permintaan berhenti aman dikirim.")
        except RuntimeError as exc:
            self._show_error(exc)

    def _retry_failed(self) -> None:
        service = self._require_service()
        if service is None:
            return
        try:
            pid = service.retry_failed_transcriptions()
            self._show_info(
                "File gagal diantrekan ulang."
                if pid is None
                else f"File gagal diantrekan ulang dan worker dimulai (PID {pid})."
            )
            QTimer.singleShot(1000, self.refresh)
        except (RuntimeError, ValueError) as exc:
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
            self._show_info("Folder audio disimpan.")
            self.refresh()
        except ValueError as exc:
            self._show_error(exc)

    def _choose_chat_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pilih Folder Ekspor Chat")
        if folder:
            self.chat_root.setText(folder)

    def _save_chat_root(self) -> None:
        service = self._require_service()
        if service is None:
            return
        try:
            service.save_chat_root(Path(self.chat_root.text()))
            self._show_info("Folder ekspor chat disimpan.")
            self.refresh()
        except ValueError as exc:
            self._show_error(exc)

    def _scan_chats(self) -> None:
        service = self._require_service()
        if service is None:
            return

        def complete(result: object) -> None:
            summary = result
            if not isinstance(summary, ChatScanSummary):
                return
            self._show_info(
                f"Ekspor chat dipindai: {summary.imported} baru, {summary.unchanged} tidak berubah, "
                f"{summary.references} referensi audio."
            )

        self._run_background("Memindai ekspor chat…", service.scan_chats, complete)

    def _match_metadata(self) -> None:
        service = self._require_service()
        if service is None:
            return

        def complete(result: object) -> None:
            summary = result
            if not isinstance(summary, MatchingSummary):
                return
            self._show_info(
                f"Pencocokan selesai: {summary.selected} cocok, {summary.ambiguous} ambigu, "
                f"{summary.unmatched} belum cocok."
            )

        self._run_background("Mencocokkan metadata secara konservatif…", service.match_metadata, complete)

    def _choose_default_model(self) -> None:
        service = self._require_service()
        if service is None:
            return
        key, accepted = QInputDialog.getItem(self, APP_NAME, "Pilih model default", ["small", "medium"], 0, False)
        if not accepted:
            return
        try:
            service.set_default_model(key)
            self._show_info(f"Model default diubah menjadi {key}. File yang sudah selesai tidak diproses ulang.")
            self.refresh()
        except Exception as exc:
            self._show_error(exc)

    def _model_key(self, title: str) -> str | None:
        key, accepted = QInputDialog.getItem(self, APP_NAME, title, ["small", "medium"], 0, False)
        return key if accepted else None

    def _download_model(self) -> None:
        service = self._require_service()
        if service is None:
            return
        key = self._model_key("Pilih model untuk diunduh")
        if key is None:
            return
        confirmed = QMessageBox.question(
            self,
            APP_NAME,
            "Model akan diunduh sebagai file bobot lokal. Audio dan transkrip tidak dikirim. Lanjutkan?",
        )  # type: ignore[call-arg]
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        self._run_background(
            f"Mengunduh dan memverifikasi model {key}…",
            lambda: service.download_model(key),
            lambda _: self._show_info(f"Model {key} siap digunakan."),
        )

    def _import_model(self) -> None:
        service = self._require_service()
        if service is None:
            return
        key = self._model_key("Pilih jenis model pada paket ZIP")
        if key is None:
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Pilih paket model", filter="Model ZIP (*.zip)")
        if not filename:
            return
        self._run_background(
            f"Mengimpor dan memverifikasi model {key}…",
            lambda: service.import_model(key, Path(filename)),
            lambda _: self._show_info(f"Model {key} siap digunakan."),
        )

    def _backup(self) -> None:
        service = self._require_service()
        if service is None:
            return
        self._run_background(
            "Membuat backup konsisten…",
            service.create_backup,
            lambda result: self._show_info(f"Backup dibuat: {Path(str(result)).name}"),
        )

    def _restore(self) -> None:
        service = self._require_service()
        if service is None:
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Pilih paket backup", filter="DNT Backup (*.dntbackup)")
        if not filename:
            return
        confirmed = QMessageBox.question(
            self,
            APP_NAME,
            "Database saat ini akan dibackup terlebih dahulu, lalu dipulihkan dari paket terpilih. Lanjutkan?",
        )  # type: ignore[call-arg]
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        self._run_background(
            "Memvalidasi dan memulihkan backup…",
            lambda: service.restore_backup(Path(filename)),
            lambda _: self._show_info("Backup berhasil dipulihkan."),
        )

    def _diagnostics(self) -> None:
        service = self._require_service()
        if service is None:
            return
        self._run_background(
            "Membuat paket diagnostik tanpa data pribadi…",
            service.create_diagnostic_bundle,
            lambda result: self._show_info(f"Paket diagnostik dibuat: {Path(str(result)).name}"),
        )

    def _reset_paging(self, _: object = None) -> None:
        self._page_offset = 0
        self.refresh()

    def _previous_page(self) -> None:
        self._page_offset = max(0, self._page_offset - self.PAGE_SIZE)
        self.refresh()

    def _next_page(self) -> None:
        self._page_offset += self.PAGE_SIZE
        self.refresh()

    def _previous_review_page(self) -> None:
        self._review_offset = max(0, self._review_offset - self.PAGE_SIZE)
        self.refresh()

    def _next_review_page(self) -> None:
        self._review_offset += self.PAGE_SIZE
        self.refresh()

    def _open_detail_from_item(self, item: QTableWidgetItem) -> None:
        table = item.tableWidget()
        if table is None:
            return
        anchor = table.item(item.row(), 0)
        if anchor is None:
            return
        audio_id = anchor.data(Qt.ItemDataRole.UserRole)
        if not isinstance(audio_id, int):
            return
        service = self._require_service()
        if service is None:
            return
        try:
            detail = service.transcript_detail(audio_id)
        except ValueError as exc:
            self._show_error(exc)
            return
        self._show_detail_editor(audio_id, detail)

    def _show_detail_editor(self, audio_id: int, detail: Any) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Detail dan koreksi")
        dialog.resize(760, 620)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"File: {detail['basename']}"))
        audio_actions = QHBoxLayout()
        play = QPushButton("Putar Audio")
        stop_audio = QPushButton("Berhenti Memutar")
        open_location = QPushButton("Buka Lokasi File")
        audio_actions.addWidget(play)
        audio_actions.addWidget(stop_audio)
        audio_actions.addWidget(open_location)
        audio_actions.addStretch(1)
        layout.addLayout(audio_actions)
        metadata = QFormLayout()
        sender = QLineEdit(str(detail["sender"] or ""))
        chat = QLineEdit(str(detail["chat"] or ""))
        timestamp = QLineEdit(str(detail["whatsapp_message_at"] or ""))
        timestamp.setPlaceholderText("2026-07-16T20:31:00+07:00 (opsional)")
        metadata.addRow("Pengirim", sender)
        metadata.addRow("Chat", chat)
        metadata.addRow(S.LABEL_WHATSAPP_TIME, timestamp)
        layout.addLayout(metadata)
        save_metadata = QPushButton("Simpan Koreksi Metadata")
        layout.addWidget(save_metadata)
        layout.addWidget(QLabel("Transkrip (dimuat hanya saat detail dibuka)"))
        transcript = QPlainTextEdit(
            str(detail["manual_transcript"] or detail["normalized_transcript"] or detail["raw_transcript"] or "")
        )
        layout.addWidget(transcript)
        verified = QCheckBox("Saya sudah memeriksa koreksi ini")
        layout.addWidget(verified)
        save_transcript = QPushButton("Simpan sebagai Versi Transkrip Manual")
        layout.addWidget(save_transcript)
        reprocess = QPushButton("Proses Ulang dengan Model Default")
        reprocess.setToolTip("Membuat attempt baru secara eksplisit. Riwayat transkrip sebelumnya tetap ada.")
        layout.addWidget(reprocess)
        close = QPushButton("Tutup")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)

        def save_metadata_action() -> None:
            service = self._require_service()
            if service is None:
                return
            try:
                service.save_manual_metadata(
                    audio_id,
                    sender=sender.text(),
                    chat=chat.text(),
                    whatsapp_message_at=timestamp.text(),
                )
                self._show_info("Koreksi metadata tersimpan. Metadata hasil parser asli tetap disimpan.")
                self.refresh()
            except ValueError as exc:
                self._show_error(exc)

        def save_transcript_action() -> None:
            service = self._require_service()
            if service is None:
                return
            try:
                service.save_manual_transcript(
                    audio_id,
                    text=transcript.toPlainText(),
                    verified=verified.isChecked(),
                )
                self._show_info("Versi transkrip manual tersimpan. Riwayat transkrip asli tidak diubah.")
                self.refresh()
            except ValueError as exc:
                self._show_error(exc)

        save_metadata.clicked.connect(save_metadata_action)
        save_transcript.clicked.connect(save_transcript_action)

        def reprocess_action() -> None:
            service = self._require_service()
            if service is None:
                return
            confirmation = QMessageBox.question(
                dialog,
                APP_NAME,
                "Buat transkripsi baru dengan model default? Riwayat sebelumnya tidak akan dihapus.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirmation != QMessageBox.StandardButton.Yes:
                return
            try:
                pid = service.reprocess_transcript(audio_id)
                self._show_info(
                    "Permintaan proses ulang dikirim."
                    if pid is None
                    else f"Worker dimulai (PID {pid}) untuk proses ulang."
                )
                self.refresh()
            except (RuntimeError, ValueError) as exc:
                self._show_error(exc)

        reprocess.clicked.connect(reprocess_action)

        def play_audio() -> None:
            service = self._require_service()
            if service is None:
                return
            try:
                self._player.setSource(QUrl.fromLocalFile(str(service.source_path(audio_id))))
                self._player.play()
            except ValueError as exc:
                self._show_error(exc)

        def open_source_location() -> None:
            service = self._require_service()
            if service is None:
                return
            try:
                source = service.source_path(audio_id)
                if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(source.parent))):
                    self._show_error(RuntimeError("Lokasi file tidak dapat dibuka."))
            except ValueError as exc:
                self._show_error(exc)

        play.clicked.connect(play_audio)
        stop_audio.clicked.connect(self._player.stop)
        open_location.clicked.connect(open_source_location)
        dialog.exec()


def run_ui(data_dir: Path | None = None, self_test: bool = False) -> int:
    paths = DataPaths(root=data_dir or default_data_root())
    first_run = not paths.config_file.exists()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyleSheet(APP_STYLESHEET)
    if first_run and not self_test:
        wizard = FirstRunWizard(paths)
        if wizard.exec() != QDialog.DialogCode.Accepted:
            return 0
        paths = DataPaths(root=wizard.selected_data_root())
    paths.ensure()
    cfg = config_mod.load(paths.config_file, paths.config_lastgood_file)
    service = ApplicationService(paths)
    service.ensure_database()
    if first_run and not self_test:
        # Persist defaults even when every optional picker was skipped so the
        # welcome wizard is shown exactly once and settings remains editable.
        config_mod.save(cfg, paths.config_file, paths.config_lastgood_file)
        audio_root = wizard.selected_audio_root()
        chat_root = wizard.selected_chat_root()
        if audio_root is not None:
            service.save_audio_root(audio_root)
        if chat_root is not None:
            service.save_chat_root(chat_root)
    setup_logging(
        paths.logs_dir,
        session_id=new_session_id(),
        role="ui",
        level=cfg.diagnostics.log_level,
        allow_transcript_bodies=cfg.privacy.log_transcript_bodies,
        keep_days=cfg.diagnostics.keep_log_days,
    )
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
        f"SELF_TEST {'PASS' if ok else 'FAIL'} visible={result.get('visible')} "
        f"title={result.get('title')!r} platform={result.get('platform')!r} version={APP_VERSION}"
    )
    return 0 if ok else 1
