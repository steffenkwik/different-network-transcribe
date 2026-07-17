"""PySide6 presentation layer for the local desktop workflow.

This module intentionally only renders views and invokes ApplicationService use
cases.  It contains no SQL and never imports the transcription engine.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import (
    QItemSelectionModel,
    QSignalBlocker,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDragLeaveEvent, QDropEvent
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
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from app import config as config_mod
from app.config import CPU_PRESETS
from app.exports.exporters import ExportResult
from app.logging_setup import new_session_id, setup_logging
from app.paths import DataPaths, default_data_root
from app.resources import strings_id as S
from app.services import worker_status
from app.services.application_service import (
    ApplicationService,
    DirectFileBatchSummary,
    TestBatchSummary,
    TranscriptPreview,
)
from app.services.chat_import_service import ChatScanSummary
from app.services.discovery_service import ScanSummary
from app.services.metadata_matching_service import MatchingSummary
from app.transcription.model_registry import MODELS
from app.ui.assets import brand_icon, install_brand_fonts
from app.ui.brand import DifferentNetworkMark
from app.ui.theme import APP_STYLESHEET
from app.version import APP_NAME, APP_VERSION


class ServiceJob(QThread):
    """Run an I/O-heavy application use case outside the Qt event thread."""

    succeeded = Signal(object)
    failed = Signal(str)
    progressed = Signal(int, int)

    def __init__(self, operation: Callable[[ServiceJob], object], parent: QWidget) -> None:
        super().__init__(parent)
        self._operation = operation

    def report(self, done: int, total: int) -> None:
        """Publish progress from the worker thread; Qt queues it to the UI thread."""
        self.progressed.emit(done, total)

    def run(self) -> None:
        try:
            self.succeeded.emit(self._operation(self))
        except Exception as exc:  # The UI receives a safe service-level message only.
            self.failed.emit(str(exc) or "Operasi tidak dapat diselesaikan.")


class AudioDropZone(QFrame):
    """Accessible drop target for a deliberate local audio batch.

    Drag-and-drop is only a convenience: the adjacent file-picker button offers
    the same workflow to keyboard and screen-reader users.  The service owns
    validation and makes no changes to the source files.
    """

    files_dropped = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("audioDropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(104)
        self.setAccessibleName("Area tarik dan lepas file audio")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        title = QLabel("Tarik file audio ke sini")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        helper = QLabel(
            "Atau pilih file dengan tombol di bawah. File tetap berada di lokasi asal, "
            "dan seluruh batch ditampilkan untuk dikonfirmasi sebelum transkripsi dimulai."
        )
        helper.setObjectName("helperText")
        helper.setWordWrap(True)
        layout.addWidget(helper)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            self._set_drag_active(True)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drag_active(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_active(False)
        files = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile() and Path(url.toLocalFile()).is_file()
        ]
        if files:
            self.files_dropped.emit(files)
            event.acceptProposedAction()
            return
        event.ignore()

    def _set_drag_active(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        style = self.style()
        style.unpolish(self)
        style.polish(self)


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
        layout.addWidget(QLabel(f"• {S.MODEL_TURBO_TITLE} — pilihan terbaik untuk arsip besar."))
        layout.addWidget(QLabel(f"• {S.MODEL_HIGH_TITLE} — untuk akurasi tertinggi dengan waktu dan RAM lebih besar."))
        layout.addWidget(QLabel("Unduh atau impor model secara eksplisit dari Pengaturan & Data. Audio tidak pernah dikirim ke cloud."))
        return page

    def _finish(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Selesai")
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(S.WIZARD_FINISH))
        return page


class TranscriptionSetupDialog(QDialog):
    """The preflight that turns an archive into a deliberate run.

    Scope is chosen against the *query*, not the visible rows, so an archive of
    thousands is one radio button rather than an impossible amount of clicking.
    The table is paged for the same reason: putting 13,000 widgets in a
    QTableWidget would freeze Qt for no benefit — nobody scrolls that far.

    The old 20-file cap that lived here was a guard-rail for the coding agent
    that built the app, and it made the product's actual purpose unreachable.
    It is replaced by confirmation that scales with the size of the request.
    """

    PAGE_SIZE = 250
    #: Batches larger than this need an explicit "yes, I mean it".
    CONFIRM_THRESHOLD = 200
    #: Above this, the confirmation also carries a duration estimate.
    ESTIMATE_THRESHOLD = 2_000

    SCOPE_SELECTED = "selected"
    SCOPE_ALL = "all"

    MODEL_NOT_INSTALLED_HINT = (
        "Model belum terpasang. Klik Unduh di bawah, atau impor dari Pengaturan & Data."
    )

    def __init__(self, service: ApplicationService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self._offset = 0
        self._candidate_total = 0
        self._checked: set[int] = set()
        self._updating = False
        self._download_jobs: set[ServiceJob] = set()
        self.setWindowTitle("Siapkan Transkripsi")
        self.resize(960, 720)
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
            "Pilihan ini hanya memengaruhi file belum selesai. Transkrip yang sudah selesai "
            "tidak akan diulang kecuali Anda meminta proses ulang dari detail file."
        )
        helper.setObjectName("helperText")
        helper.setWordWrap(True)
        layout.addWidget(helper)
        self.summary_label = QLabel()
        self.summary_label.setObjectName("statusPill")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        layout.addWidget(self._model_section())
        layout.addWidget(self._scope_section())
        layout.addLayout(self._table_actions())
        layout.addWidget(self._file_table(), 1)
        layout.addLayout(self._pagination())

        self.confirm_large = QCheckBox()
        self.confirm_large.setVisible(False)
        self.confirm_large.toggled.connect(self._update_start_state)
        layout.addWidget(self.confirm_large)

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
        self._load_page()

    # ---------------------------------------------------------------- layout

    def _model_section(self) -> QFrame:
        self.model_status = self.service.model_status()
        self.model_meta: dict[str, tuple[str, str]] = {}
        self.model_buttons: dict[str, QRadioButton] = {}
        self.model_download_buttons: dict[str, QPushButton] = {}
        self.model_group = QButtonGroup(self)

        section = QFrame()
        section.setObjectName("workflowCard")
        outer = QVBoxLayout(section)
        outer.setContentsMargins(16, 14, 16, 14)
        title = QLabel("1. Model lokal")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)
        outer.addWidget(
            QLabel("Model dimuat sekali oleh worker dan tetap berada di komputer ini.")
        )
        row = QHBoxLayout()
        for key, model_title, description in (
            ("small", S.MODEL_SMALL_TITLE, "Cepat; direkomendasikan untuk mulai."),
            ("medium", S.MODEL_MEDIUM_TITLE, "Lebih akurat; membutuhkan waktu lebih lama."),
            ("turbo", S.MODEL_TURBO_TITLE, "Akurasi tinggi dengan kecepatan mendekati Small."),
            ("high", S.MODEL_HIGH_TITLE, "Paling akurat; paling lambat dan butuh RAM/disk lebih besar."),
        ):
            row.addWidget(self._model_cell(key, model_title, description))
        outer.addLayout(row)

        self.model_hint = QLabel()
        self.model_hint.setObjectName("subtle")
        self.model_hint.setWordWrap(True)
        outer.addWidget(self.model_hint)
        return section

    def _scope_section(self) -> QFrame:
        section = QFrame()
        section.setObjectName("workflowCard")
        scope_layout = QVBoxLayout(section)
        scope_layout.setContentsMargins(16, 14, 16, 14)
        title = QLabel("2. Cakupan")
        title.setObjectName("sectionTitle")
        scope_layout.addWidget(title)
        self.scope_all = QRadioButton()
        self.scope_all.setProperty("scope", self.SCOPE_ALL)
        self.scope_all.setToolTip(
            "Mengaktifkan seluruh file belum selesai di folder yang sedang aktif. "
            "File yang sudah selesai tidak pernah diulang."
        )
        self.scope_selected = QRadioButton("Hanya file yang saya centang di daftar bawah")
        self.scope_selected.setProperty("scope", self.SCOPE_SELECTED)
        self.scope_group = QButtonGroup(self)
        for button in (self.scope_all, self.scope_selected):
            self.scope_group.addButton(button)
            scope_layout.addWidget(button)
        self.scope_all.setChecked(True)
        self.scope_group.buttonClicked.connect(self._scope_changed)
        return section

    def _table_actions(self) -> QHBoxLayout:
        actions = QHBoxLayout()
        self.select_visible_button = QPushButton("Centang halaman ini")
        self.select_visible_button.clicked.connect(lambda: self._check_visible(True))
        self.clear_selection_button = QPushButton("Kosongkan semua centang")
        self.clear_selection_button.clicked.connect(self._clear_all_checks)
        actions.addWidget(self.select_visible_button)
        actions.addWidget(self.clear_selection_button)
        actions.addStretch(1)
        self.selection_count_label = QLabel()
        self.selection_count_label.setObjectName("statusPill")
        actions.addWidget(self.selection_count_label)
        return actions

    def _file_table(self) -> QTableWidget:
        self.file_table = QTableWidget(0, 5)
        self.file_table.setHorizontalHeaderLabels(
            ["Proses", "Nama file", "Durasi", "Status", "Lokasi relatif"]
        )
        self.file_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.file_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.file_table.itemChanged.connect(self._selection_changed)
        header = self.file_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        return self.file_table

    def _pagination(self) -> QHBoxLayout:
        pagination = QHBoxLayout()
        self.previous_button = QPushButton("Sebelumnya")
        self.previous_button.clicked.connect(self._previous_page)
        self.next_button = QPushButton("Berikutnya")
        self.next_button.clicked.connect(self._next_page)
        pagination.addWidget(self.previous_button)
        pagination.addWidget(self.next_button)
        self.file_help = QLabel()
        self.file_help.setObjectName("subtle")
        pagination.addWidget(self.file_help)
        pagination.addStretch(1)
        return pagination

    # ----------------------------------------------------------------- data

    @staticmethod
    def _model_label(title: str, description: str, installed: bool) -> str:
        return f"{title}\n{description}\n{'Terpasang' if installed else 'Belum terpasang'}"

    def _model_cell(self, key: str, title: str, description: str) -> QWidget:
        models = self.model_status.get("models", {})
        entry = models.get(key, {}) if isinstance(models, dict) else {}
        installed = bool(entry.get("installed")) if isinstance(entry, dict) else False
        self.model_meta[key] = (title, description)

        cell = QWidget()
        box = QVBoxLayout(cell)
        box.setContentsMargins(0, 0, 0, 0)
        radio = QRadioButton(self._model_label(title, description, installed))
        radio.setProperty("modelKey", key)
        radio.setEnabled(installed)
        radio.setToolTip(title if installed else self.MODEL_NOT_INSTALLED_HINT)
        self.model_buttons[key] = radio
        self.model_group.addButton(radio)
        box.addWidget(radio)

        download = QPushButton("Unduh")
        download.setToolTip(
            f"Unduh bobot model {key} dari Hugging Face. Audio dan transkrip tidak dikirim."
        )
        download.clicked.connect(lambda _checked=False, k=key: self._download_model_inline(k))
        download.setVisible(not installed)
        self.model_download_buttons[key] = download
        box.addWidget(download)
        box.addStretch(1)
        return cell

    def _download_model_inline(self, key: str) -> None:
        """Download a model from the preflight so Turbo/High are reachable here.

        The old dialog only disabled the radio for a missing model and pointed at
        Settings, which left Turbo and High effectively unusable from the one
        place a run is actually started. Blueprint §5.1 asks for an inline
        download; this runs it off the UI thread and re-enables the model in place.
        """
        if self.service is None:
            return
        confirmed = QMessageBox.question(
            self,
            APP_NAME,
            f"Unduh model {key} sebagai bobot lokal? Unduhan cukup besar dan bisa memakan "
            "beberapa menit. Audio dan transkrip tidak pernah dikirim.",
        )  # type: ignore[call-arg]
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        for button in self.model_download_buttons.values():
            button.setEnabled(False)
        self.model_hint.setText(
            f"Mengunduh model {key}… biarkan jendela ini terbuka; proses bisa beberapa menit."
        )
        job = ServiceJob(lambda _job: self.service.download_model(key), self)
        self._download_jobs.add(job)

        def on_success(_result: object) -> None:
            self.model_hint.setText(f"Model {key} siap digunakan.")
            self._reload_model_status_and_refresh(select=key)

        def on_failure(message: str) -> None:
            self.model_hint.setText("")
            for button in self.model_download_buttons.values():
                button.setEnabled(True)
            QMessageBox.warning(self, APP_NAME, message)  # type: ignore[call-arg]

        job.succeeded.connect(on_success)
        job.failed.connect(on_failure)
        job.finished.connect(lambda: self._download_jobs.discard(job))
        job.start()

    def _reload_model_status_and_refresh(self, select: str | None = None) -> None:
        self.model_status = self.service.model_status()
        raw = self.model_status.get("models", {})
        models = raw if isinstance(raw, dict) else {}
        for key, radio in self.model_buttons.items():
            entry = models.get(key, {})
            installed = bool(entry.get("installed")) if isinstance(entry, dict) else False
            title, description = self.model_meta[key]
            radio.setText(self._model_label(title, description, installed))
            radio.setEnabled(installed)
            radio.setToolTip(title if installed else self.MODEL_NOT_INSTALLED_HINT)
            download = self.model_download_buttons.get(key)
            if download is not None:
                download.setVisible(not installed)
                download.setEnabled(not installed)
        chosen = self.model_buttons.get(select) if select else None
        if chosen is not None and chosen.isEnabled():
            chosen.setChecked(True)
        self._update_start_state()

    def _load_models(self) -> None:
        default = str(self.model_status.get("default_model", "small"))
        preferred = self.model_buttons.get(default)
        if preferred is not None and preferred.isEnabled():
            preferred.setChecked(True)
        else:
            for button in self.model_buttons.values():
                if button.isEnabled():
                    button.setChecked(True)
                    break
        self.model_group.buttonClicked.connect(self._update_start_state)

    def selected_model(self) -> str | None:
        button = self.model_group.checkedButton()
        return None if button is None else str(button.property("modelKey"))

    def scope(self) -> str:
        button = self.scope_group.checkedButton()
        return self.SCOPE_ALL if button is None else str(button.property("scope"))

    def _load_page(self) -> None:
        page = self.service.transcription_candidates(limit=self.PAGE_SIZE, offset=self._offset)
        self._candidate_total = page.total
        self._updating = True
        try:
            self.file_table.setRowCount(len(page.rows))
            for index, row in enumerate(page.rows):
                audio_id = int(row["id"])
                check = QTableWidgetItem()
                check.setData(Qt.ItemDataRole.UserRole, audio_id)
                check.setCheckState(
                    Qt.CheckState.Checked if audio_id in self._checked else Qt.CheckState.Unchecked
                )
                self.file_table.setItem(index, 0, check)
                self.file_table.setItem(index, 1, QTableWidgetItem(str(row["basename"])))
                duration = row["duration_seconds"]
                duration_text = "-" if duration is None else f"{float(duration):.1f} dtk"
                self.file_table.setItem(index, 2, QTableWidgetItem(duration_text))
                self.file_table.setItem(index, 3, QTableWidgetItem(str(row["current_state"])))
                self.file_table.setItem(index, 4, QTableWidgetItem(str(row["current_relative_path"])))
        finally:
            self._updating = False
        self.scope_all.setText(f"Semua file belum selesai ({self._candidate_total:,} file)".replace(",", "."))
        first = 0 if self._candidate_total == 0 else self._offset + 1
        last = min(self._candidate_total, self._offset + self.PAGE_SIZE)
        self.file_help.setText(f"Menampilkan {first}-{last} dari {self._candidate_total}")
        self.previous_button.setEnabled(self._offset > 0)
        self.next_button.setEnabled(self._offset + self.PAGE_SIZE < self._candidate_total)
        self._update_start_state()

    def _previous_page(self) -> None:
        self._offset = max(0, self._offset - self.PAGE_SIZE)
        self._load_page()

    def _next_page(self) -> None:
        self._offset += self.PAGE_SIZE
        self._load_page()

    # ------------------------------------------------------------ selection

    def _selection_changed(self, item: QTableWidgetItem) -> None:
        """Track ticks in a set so they survive paging."""
        if self._updating or item.column() != 0:
            return
        audio_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(audio_id, int):
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._checked.add(audio_id)
        else:
            self._checked.discard(audio_id)
        self._update_start_state()

    def _check_visible(self, checked: bool) -> None:
        self._updating = True
        try:
            for row in range(self.file_table.rowCount()):
                item = self.file_table.item(row, 0)
                if item is None:
                    continue
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                audio_id = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(audio_id, int):
                    if checked:
                        self._checked.add(audio_id)
                    else:
                        self._checked.discard(audio_id)
        finally:
            self._updating = False
        self._update_start_state()

    def _clear_all_checks(self) -> None:
        self._checked.clear()
        self._load_page()

    def _scope_changed(self, *_: object) -> None:
        selecting = self.scope() == self.SCOPE_SELECTED
        self.file_table.setEnabled(selecting)
        self.select_visible_button.setEnabled(selecting)
        self.clear_selection_button.setEnabled(selecting)
        self._update_start_state()

    # --------------------------------------------------------------- gating

    def planned_count(self) -> int:
        return self._candidate_total if self.scope() == self.SCOPE_ALL else len(self._checked)

    def _update_start_state(self, *_: object) -> None:
        planned = self.planned_count()
        model_key = self.selected_model()
        self.selection_count_label.setText(f"{planned:,} akan diproses".replace(",", "."))

        needs_confirmation = planned > self.CONFIRM_THRESHOLD
        self.confirm_large.setVisible(needs_confirmation)
        if not needs_confirmation and self.confirm_large.isChecked():
            self.confirm_large.setChecked(False)
        if needs_confirmation:
            self.confirm_large.setText(
                f"Saya mengerti ini akan memproses {planned:,} file dan berjalan lama.".replace(",", ".")
            )

        if model_key is None:
            self.summary_label.setText("Belum ada model terpasang.")
            self.validation_label.setText(
                "Pasang salah satu model terlebih dahulu di Pengaturan & Data."
            )
            self.start_button.setEnabled(False)
            return

        self.summary_label.setText(self._forecast_text(planned, model_key))
        if planned == 0:
            self.validation_label.setText(
                "Belum ada file yang dipilih. Tambahkan audio dari Beranda, tarik dan lepas file, "
                "atau lakukan Scan File Baru."
                if self._candidate_total == 0
                else "Centang minimal satu file, atau pilih cakupan semua file."
            )
            self.start_button.setEnabled(False)
            return
        if needs_confirmation and not self.confirm_large.isChecked():
            self.validation_label.setText("Centang konfirmasi di atas untuk menjalankan batch besar.")
            self.start_button.setEnabled(False)
            return
        self.validation_label.setText(
            "File yang tidak dipilih disimpan sebagai dikecualikan dan tidak ikut antrean."
        )
        self.start_button.setEnabled(True)

    def _forecast_text(self, planned: int, model_key: str) -> str:
        if planned == 0:
            return f"{self._candidate_total:,} file belum selesai di folder aktif.".replace(",", ".")
        estimate = self.service.run_estimate(model_key)
        readable = worker_status.format_duration(estimate.total_seconds(planned))
        if planned <= self.ESTIMATE_THRESHOLD and not estimate.measured:
            # Below the threshold a rough guess adds noise rather than help.
            return f"{planned:,} file akan diproses.".replace(",", ".")
        basis = "berdasarkan kecepatan komputer ini" if estimate.measured else "perkiraan kasar"
        return f"{planned:,} file · perkiraan ±{readable} ({basis})".replace(",", ".")

    def _commit_and_accept(self) -> None:
        model_key = self.selected_model()
        if model_key is None:
            return
        try:
            self.service.set_default_model(model_key)
            if self.scope() == self.SCOPE_ALL:
                self.service.set_all_transcription_enabled(enabled=True)
            else:
                self.service.replace_transcription_selection(sorted(self._checked))
        except (RuntimeError, ValueError) as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))  # type: ignore[call-arg]
            return
        self.accept()


class ExportSetupDialog(QDialog):
    """Let users name an export and choose formats before any files are written."""

    def __init__(self, default_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Buat Hasil Transkripsi")
        self.setModal(True)
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        heading = QLabel("Pilih nama dan format hasil")
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        helper = QLabel(
            "Nama kosong memakai nama folder audio aktif. Setiap hasil disimpan dalam foldernya sendiri, "
            "jadi lokasi berkas selalu jelas."
        )
        helper.setObjectName("helperText")
        helper.setWordWrap(True)
        layout.addWidget(helper)
        form = QFormLayout()
        self.name_input = QLineEdit(default_name)
        self.name_input.setPlaceholderText(default_name)
        self.name_input.setToolTip("Contoh: Rapat Tim Juli. Karakter nama file yang tidak aman diganti otomatis.")
        form.addRow("Nama hasil", self.name_input)
        layout.addLayout(form)
        layout.addWidget(QLabel("Format yang dibuat"))
        self.markdown = QCheckBox("Markdown (.md) — mudah dibaca dan diedit")
        self.markdown.setChecked(True)
        self.text = QCheckBox("Teks biasa (.txt)")
        self.text.setChecked(True)
        self.csv = QCheckBox("CSV (.csv) — untuk spreadsheet")
        self.jsonl = QCheckBox("JSONL (.jsonl) — untuk data terstruktur")
        for choice in (self.markdown, self.text, self.csv, self.jsonl):
            choice.toggled.connect(self._validate)
            layout.addWidget(choice)
        self.individual = QCheckBox("Tambahkan satu Markdown per rekaman")
        self.individual.setEnabled(True)
        self.markdown.toggled.connect(self.individual.setEnabled)
        layout.addWidget(self.individual)
        self.validation = QLabel()
        self.validation.setObjectName("helperText")
        layout.addWidget(self.validation)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.create_button = QPushButton("Buat Hasil")
        self.create_button.setObjectName("primaryButton")
        self.create_button.clicked.connect(self.accept)
        buttons.addButton(self.create_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._validate()

    def formats(self) -> set[str]:
        return {
            key
            for key, checked in (
                ("markdown", self.markdown.isChecked()),
                ("text", self.text.isChecked()),
                ("csv", self.csv.isChecked()),
                ("jsonl", self.jsonl.isChecked()),
            )
            if checked
        }

    def _validate(self, *_: object) -> None:
        valid = bool(self.formats())
        self.validation.setText("" if valid else "Pilih minimal satu format hasil.")
        self.create_button.setEnabled(valid)


class TranscriptPreviewDialog(QDialog):
    """Bounded local transcript preview, including metadata and timeframe."""

    def __init__(self, entries: list[TranscriptPreview], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entries = entries
        self.setWindowTitle("Preview Hasil Transkripsi")
        self.resize(940, 660)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        title = QLabel("Preview hasil transkripsi")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        helper = QLabel(
            f"Menampilkan {len(entries)} hasil terbaru dari database lokal. Pilih baris untuk melihat teks, "
            "waktu WhatsApp, durasi, model, dan status kualitas."
        )
        helper.setObjectName("helperText")
        helper.setWordWrap(True)
        layout.addWidget(helper)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["File", "Waktu", "Durasi", "Pengirim / Chat", "Model", "Kualitas"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        for index, entry in enumerate(entries):
            self.table.insertRow(index)
            values = (
                entry.basename,
                entry.whatsapp_timestamp or entry.completed_at or "Waktu tidak diketahui",
                "-" if entry.duration_seconds is None else f"{entry.duration_seconds:.1f} dtk",
                " · ".join(value for value in (entry.sender, entry.chat) if value) or "-",
                entry.model_name or "-",
                entry.quality_status or "-",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, index)
                self.table.setItem(index, column, item)
        self.table.itemSelectionChanged.connect(self._show_selected)
        layout.addWidget(self.table, 1)
        layout.addWidget(QLabel("Teks transkripsi"))
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(140)
        layout.addWidget(self.text)
        close = QPushButton("Tutup")
        close.clicked.connect(self.accept)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        if entries:
            self.table.selectRow(0)

    def _show_selected(self) -> None:
        selected = self.table.selectedItems()
        if not selected:
            self.text.clear()
            return
        index = selected[0].data(Qt.ItemDataRole.UserRole)
        if isinstance(index, int) and 0 <= index < len(self.entries):
            self.text.setPlainText(self.entries[index].transcript)


class MainWindow(QMainWindow):
    #: Fallbacks only; the live values come from config via `ui_settings()`.
    PAGE_SIZE = 100
    STATUS_TICK_MS = 750
    #: The slowest acceptable staleness for tables/metrics while a worker runs.
    AUTO_REFRESH_SECONDS = 5.0
    #: Typing in a search box should not run a query per keystroke.
    SEARCH_DEBOUNCE_MS = 300
    SETTINGS_PAGE_INDEX = 3

    def __init__(self, paths: DataPaths | None = None, service: ApplicationService | None = None) -> None:
        super().__init__()
        self.paths = paths
        self.service = service
        self._jobs: set[ServiceJob] = set()
        self._page_offset = 0
        self._review_offset = 0
        self._table_fingerprints: dict[int, tuple[object, ...]] = {}
        self._worker_active = False
        self._previewed_finished_sessions: set[str] = set()
        self._last_export_dir: Path | None = None
        self._last_data_refresh = 0.0
        # Honour the two UI settings the config has always validated; leaving
        # them unread made them a promise the app never kept.
        ui_config = service.ui_settings() if service is not None else config_mod.UiConfig()
        self.page_size = ui_config.page_size
        self.status_tick_ms = ui_config.poll_interval_ms
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
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(self.SEARCH_DEBOUNCE_MS)
        self._search_debounce.timeout.connect(self._reset_paging)
        self._worker_status_timer = QTimer(self)
        self._worker_status_timer.setInterval(self.status_tick_ms)
        self._worker_status_timer.timeout.connect(self._tick)
        self._worker_status_timer.start()

    def _tick(self) -> None:
        """Cheap periodic work only.

        Repopulating tables on every tick used to discard the user's row
        selection and overwrite the settings fields while they were typing, so
        the tick now reads the small status file and refreshes heavy data only
        while a worker is actually changing it.
        """
        self._refresh_worker_status()
        if self.service is None or not self._worker_active:
            return
        if time.monotonic() - self._last_data_refresh >= self.AUTO_REFRESH_SECONDS:
            self.refresh()

    def _sync_navigation(self, current_index: int) -> None:
        """Keep the selected sidebar destination obvious for mouse and keyboard users."""
        for index, button in enumerate(self._nav_buttons):
            button.setChecked(index == current_index)
        if current_index == self.SETTINGS_PAGE_INDEX:
            # Folder fields are loaded on entry only; a timer must never
            # overwrite a path the user is in the middle of typing.
            self._load_settings_fields()

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
        self.metric_review = self._metric_card("Perlu ditinjau", "0")
        self.metric_review.setToolTip(
            "Jumlah yang sama dengan halaman Perlu Ditinjau. Angka ini bisa beririsan "
            "dengan Selesai, karena transkrip yang sudah jadi pun bisa perlu diperiksa."
        )
        metrics.addWidget(self.metric_total, 0, 0)
        metrics.addWidget(self.metric_done, 0, 1)
        metrics.addWidget(self.metric_pending, 0, 2)
        metrics.addWidget(self.metric_review, 0, 3)
        layout.addLayout(metrics)
        # Without this line the four cards silently fail to add up to Total VN.
        self.metric_breakdown = QLabel()
        self.metric_breakdown.setObjectName("subtle")
        self.metric_breakdown.setWordWrap(True)
        layout.addWidget(self.metric_breakdown)

        add_files_card = QFrame()
        add_files_card.setObjectName("workflowCard")
        add_files_layout = QVBoxLayout(add_files_card)
        add_files_layout.setContentsMargins(18, 16, 18, 16)
        add_files_layout.setSpacing(12)
        add_files_heading = QHBoxLayout()
        add_files_copy = QVBoxLayout()
        add_files_title = QLabel("Tambahkan audio langsung")
        add_files_title.setObjectName("sectionTitle")
        add_files_copy.addWidget(add_files_title)
        add_files_info = QLabel(
            "Tidak perlu menyiapkan folder baru. Pilih beberapa file atau tarik dan lepas ke area ini. "
            "Audio tidak disalin, dipindahkan, atau diubah."
        )
        add_files_info.setObjectName("helperText")
        add_files_info.setWordWrap(True)
        add_files_copy.addWidget(add_files_info)
        add_files_heading.addLayout(add_files_copy, 1)
        self.add_audio_button = QPushButton("Pilih File Audio")
        self.add_audio_button.setToolTip(
            "Pilih satu file atau ribuan sekaligus. Tidak ada yang diproses sebelum Anda "
            "memilih model dan menekan Mulai."
        )
        self.add_audio_button.clicked.connect(self._choose_audio_files)
        add_files_heading.addWidget(self.add_audio_button)
        add_files_layout.addLayout(add_files_heading)
        self.audio_drop_zone = AudioDropZone(add_files_card)
        self.audio_drop_zone.files_dropped.connect(self._add_audio_files)
        add_files_layout.addWidget(self.audio_drop_zone)
        layout.addWidget(add_files_card)

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
        output_info = QLabel("Pilih nama dan format hasil sebelum dibuat. Pembuatan hasil tidak mentranskripsi ulang audio.")
        output_info.setObjectName("helperText")
        output_info.setWordWrap(True)
        output_copy.addWidget(output_info)
        self.output_path_label = QLabel()
        self.output_path_label.setObjectName("subtle")
        self.output_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.output_path_label.setWordWrap(True)
        if self.paths is not None:
            self.output_path_label.setText(f"Folder hasil: {self.paths.output_dir}")
        else:
            self.output_path_label.setText("Folder hasil akan ditampilkan setelah aplikasi siap.")
        output_copy.addWidget(self.output_path_label)
        output_layout.addLayout(output_copy, 1)
        self.export_button = QPushButton(S.ACTION_EXPORT)
        self.export_button.clicked.connect(self._export)
        output_layout.addWidget(self.export_button)
        self.preview_button = QPushButton("Preview Transkripsi")
        self.preview_button.setToolTip("Tampilkan teks, waktu, durasi, model, dan kualitas hasil terbaru.")
        self.preview_button.clicked.connect(self._show_transcript_preview)
        output_layout.addWidget(self.preview_button)
        self.open_last_export_button = QPushButton("Buka Hasil Terakhir")
        self.open_last_export_button.setEnabled(False)
        self.open_last_export_button.setToolTip("Membuka folder hasil spesifik dari ekspor terakhir.")
        self.open_last_export_button.clicked.connect(self._open_last_export)
        output_layout.addWidget(self.open_last_export_button)
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
        self.search_input.textChanged.connect(self._queue_search_refresh)
        self.transcript_search_input = QLineEdit()
        self.transcript_search_input.setPlaceholderText("Cari isi transkrip")
        self.transcript_search_input.textChanged.connect(self._queue_search_refresh)
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
        for key in MODELS:
            self.model_filter.addItem(key.capitalize(), key)
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
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.itemDoubleClicked.connect(self._open_detail_from_item)
        self.table.itemSelectionChanged.connect(self._update_history_action_state)
        layout.addWidget(self.table)
        pagination = QHBoxLayout()
        self.delete_history_button = QPushButton("Hapus Riwayat Terpilih")
        self.delete_history_button.setObjectName("dangerButton")
        self.delete_history_button.setToolTip(
            "Hapus transkrip dan koreksi pada baris terpilih. Audio serta chat sumber tidak dihapus."
        )
        self.delete_history_button.setEnabled(False)
        self.delete_history_button.clicked.connect(self._clear_selected_history)
        pagination.addWidget(self.delete_history_button)
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
        table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        return table

    def _settings(self) -> QWidget:
        """Grouped settings where every visible control genuinely takes effect.

        The previous page was a flat column of buttons that exposed folders and
        models only, while the config file carried validated settings nothing
        ever read. A setting that does not do what it says is worse than a
        missing one, so anything shown here is wired through to the engine,
        the exporter, or the queue.
        """
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(30, 28, 30, 28)
        outer.setSpacing(10)
        eyebrow = QLabel("KONFIGURASI LOKAL")
        eyebrow.setObjectName("eyebrow")
        outer.addWidget(eyebrow)
        title = QLabel(S.NAV_SETTINGS)
        title.setObjectName("pageTitle")
        outer.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._settings_sources_tab(), "Sumber Data")
        tabs.addTab(self._settings_transcription_tab(), "Transkripsi")
        tabs.addTab(self._settings_export_tab(), "Ekspor")
        tabs.addTab(self._settings_data_tab(), "Data && Diagnostik")
        outer.addWidget(tabs, 1)
        return page

    @staticmethod
    def _scroll(inner: QWidget) -> QScrollArea:
        """Keep a tab usable on a small laptop screen."""
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setWidget(inner)
        return area

    def _settings_sources_tab(self) -> QWidget:
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(4, 12, 4, 12)
        layout.setSpacing(10)

        audio_title = QLabel("Folder arsip audio")
        audio_title.setObjectName("sectionTitle")
        layout.addWidget(audio_title)
        audio_help = QLabel(
            "Folder ini yang dipindai oleh Scan File Baru. File yang Anda tambahkan lewat "
            "Pilih File Audio tidak pernah menggantikannya."
        )
        audio_help.setObjectName("helperText")
        audio_help.setWordWrap(True)
        layout.addWidget(audio_help)
        self.audio_root = QLineEdit()
        self.audio_root.setPlaceholderText("Belum ada folder audio")
        layout.addWidget(self.audio_root)
        audio_actions = QHBoxLayout()
        choose_audio = QPushButton("Pilih Folder Audio")
        choose_audio.clicked.connect(self._choose_audio_root)
        save_audio = QPushButton("Simpan Folder Audio")
        save_audio.clicked.connect(self._save_audio_root)
        audio_actions.addWidget(choose_audio)
        audio_actions.addWidget(save_audio)
        audio_actions.addStretch(1)
        layout.addLayout(audio_actions)

        direct_title = QLabel("Folder batch langsung")
        direct_title.setObjectName("sectionTitle")
        layout.addWidget(direct_title)
        self.direct_roots_label = QLabel()
        self.direct_roots_label.setObjectName("subtle")
        self.direct_roots_label.setWordWrap(True)
        layout.addWidget(self.direct_roots_label)
        clear_direct = QPushButton("Bersihkan Folder Batch Langsung")
        clear_direct.setToolTip(
            "Mengeluarkan folder tersebut dari cakupan. Tidak ada file audio yang dihapus."
        )
        clear_direct.clicked.connect(self._clear_direct_roots)
        layout.addWidget(clear_direct, alignment=Qt.AlignmentFlag.AlignLeft)

        chat_title = QLabel("Folder ekspor chat WhatsApp")
        chat_title.setObjectName("sectionTitle")
        layout.addWidget(chat_title)
        self.chat_root = QLineEdit()
        self.chat_root.setPlaceholderText("Opsional: folder berisi ekspor chat .txt")
        layout.addWidget(self.chat_root)
        chat_actions = QHBoxLayout()
        for label, slot in (
            ("Pilih Folder Ekspor Chat", self._choose_chat_root),
            ("Simpan Folder Ekspor Chat", self._save_chat_root),
            ("Scan Ekspor Chat", self._scan_chats),
            ("Cocokkan Metadata", self._match_metadata),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            chat_actions.addWidget(button)
        chat_actions.addStretch(1)
        layout.addLayout(chat_actions)
        layout.addStretch(1)
        return self._scroll(inner)

    def _settings_transcription_tab(self) -> QWidget:
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(4, 12, 4, 12)
        layout.setSpacing(10)

        model_notice = QLabel(S.MODEL_CHANGE_NOTICE)
        model_notice.setObjectName("helperText")
        model_notice.setWordWrap(True)
        layout.addWidget(model_notice)
        self.model_status_label = QLabel("Status model belum dibaca.")
        self.model_status_label.setWordWrap(True)
        layout.addWidget(self.model_status_label)
        model_actions = QHBoxLayout()
        for label, slot in (
            ("Pilih Model Default", self._choose_default_model),
            ("Unduh Model", self._download_model),
            ("Impor Model ZIP", self._import_model),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            model_actions.addWidget(button)
        model_actions.addStretch(1)
        layout.addLayout(model_actions)

        form = QFormLayout()
        self.language_choice = QComboBox()
        self.language_choice.addItem("Indonesia (id)", "id")
        self.language_choice.addItem("Deteksi otomatis", "auto")
        form.addRow("Bahasa", self.language_choice)

        self.task_choice = QComboBox()
        self.task_choice.addItem("Transkripsi (bahasa asli)", "transcribe")
        self.task_choice.addItem("Terjemahkan ke Inggris", "translate")
        self.task_choice.setToolTip(
            "Whisper hanya bisa menerjemahkan ke bahasa Inggris. Semuanya tetap berjalan di komputer ini."
        )
        form.addRow("Mode", self.task_choice)

        self.cpu_choice = QComboBox()
        for preset in CPU_PRESETS:
            self.cpu_choice.addItem(preset.capitalize(), preset)
        self.cpu_choice.currentIndexChanged.connect(self._preview_cpu_threads)
        form.addRow("Penggunaan CPU", self.cpu_choice)
        self.cpu_threads_label = QLabel()
        self.cpu_threads_label.setObjectName("subtle")
        form.addRow("", self.cpu_threads_label)

        self.batched_choice = QCheckBox("Proses dalam batch (lebih cepat, butuh RAM lebih)")
        form.addRow("Kecepatan", self.batched_choice)
        self.batch_size_choice = QSpinBox()
        self.batch_size_choice.setRange(1, 32)
        form.addRow("Ukuran batch", self.batch_size_choice)
        self.vad_choice = QCheckBox("Lewati bagian tanpa suara (disarankan)")
        form.addRow("VAD", self.vad_choice)
        self.beam_choice = QSpinBox()
        self.beam_choice.setRange(1, 10)
        self.beam_choice.setToolTip("Nilai lebih tinggi sedikit lebih akurat dan lebih lambat.")
        form.addRow("Beam size", self.beam_choice)
        layout.addLayout(form)

        save = QPushButton("Simpan Pengaturan Transkripsi")
        save.setObjectName("primaryButton")
        save.clicked.connect(self._save_transcription_settings)
        layout.addWidget(save, alignment=Qt.AlignmentFlag.AlignLeft)
        applies = QLabel(
            "Berlaku saat worker berikutnya dimulai. Transkrip yang sudah selesai tidak pernah "
            "diulang karena perubahan pengaturan."
        )
        applies.setObjectName("helperText")
        applies.setWordWrap(True)
        layout.addWidget(applies)
        layout.addStretch(1)
        return self._scroll(inner)

    def _settings_export_tab(self) -> QWidget:
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(4, 12, 4, 12)
        layout.setSpacing(10)
        intro = QLabel(
            "Markdown harian, TXT, CSV, dan JSONL selalu dibuat. Opsi di bawah menambah "
            "keluaran atau mengubah isinya."
        )
        intro.setObjectName("helperText")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.export_individual_choice = QCheckBox("Buat juga satu berkas Markdown per transkrip")
        layout.addWidget(self.export_individual_choice)
        self.export_generated_at_choice = QCheckBox(
            "Sertakan waktu pembuatan di Markdown (mematikan hasil yang identik byte-per-byte)"
        )
        layout.addWidget(self.export_generated_at_choice)
        save = QPushButton("Simpan Pengaturan Ekspor")
        save.setObjectName("primaryButton")
        save.clicked.connect(self._save_export_settings)
        layout.addWidget(save, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return self._scroll(inner)

    def _settings_data_tab(self) -> QWidget:
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(4, 12, 4, 12)
        layout.setSpacing(10)
        self.data_root_label = QLabel()
        self.data_root_label.setObjectName("subtle")
        self.data_root_label.setWordWrap(True)
        self.data_root_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if self.paths is not None:
            self.data_root_label.setText(f"Folder data: {self.paths.root}")
        layout.addWidget(self.data_root_label)
        for label, slot, tip in (
            ("Buka Folder Data", self._open_data_root, "Berisi database, model, hasil, log, dan backup."),
            ("Backup Sekarang", self._backup, "Membuat paket .dntbackup dari database saat ini."),
            ("Pulihkan Paket", self._restore, "Database saat ini dibackup lebih dulu."),
            (
                "Buat Paket Diagnostik Aman",
                self._diagnostics,
                "Berisi log teknis tanpa transkrip, nama, atau audio.",
            ),
        ):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return self._scroll(inner)

    def refresh(self) -> None:
        """Reload derived data. Deliberately never touches editable settings fields."""
        self._last_data_refresh = time.monotonic()
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
        self.metric_breakdown.setText(
            f"Rincian Total VN: {counts.completed} selesai · {counts.pending} belum diproses · "
            f"{counts.failed} gagal atau sumber hilang · {counts.excluded} dikecualikan · "
            f"{counts.no_speech} tanpa suara."
        )
        self._refresh_transcript_table()
        self._refresh_review_table()
        self._refresh_model_status()
        self._refresh_worker_status()

    def _load_settings_fields(self) -> None:
        """Read settings from config into the editable controls."""
        if self.service is None:
            return
        audio_root = self.service.configured_audio_root()
        chat_root = self.service.configured_chat_root()
        self.audio_root.setText("" if audio_root is None else str(audio_root))
        self.chat_root.setText("" if chat_root is None else str(chat_root))
        direct = self.service.configured_direct_roots()
        self.direct_roots_label.setText(
            "Belum ada. Folder muncul di sini saat Anda memakai Pilih File Audio atau tarik-lepas."
            if not direct
            else "Ikut dicakup: " + " · ".join(str(root) for root in direct)
        )
        settings = self.service.transcription_settings()
        _select_data(self.language_choice, settings.language)
        _select_data(self.task_choice, settings.task)
        _select_data(self.cpu_choice, settings.cpu_preset)
        self.batched_choice.setChecked(settings.batched_inference)
        self.batch_size_choice.setValue(settings.batch_size)
        self.vad_choice.setChecked(settings.vad_filter)
        self.beam_choice.setValue(settings.beam_size)
        self._preview_cpu_threads()
        export = self.service.export_settings()
        self.export_individual_choice.setChecked(export.markdown_individual)
        self.export_generated_at_choice.setChecked(export.include_generated_at)

    def _preview_cpu_threads(self, *_: object) -> None:
        """Show the concrete thread count, because a preset name alone is opaque."""
        preset = str(self.cpu_choice.currentData() or "seimbang")
        threads = config_mod.resolve_cpu_threads(preset)
        self.cpu_threads_label.setText(
            f"Menggunakan {threads} dari {os.cpu_count() or threads} thread pada komputer ini."
        )

    def _save_transcription_settings(self) -> None:
        service = self._require_service()
        if service is None:
            return
        try:
            service.save_transcription_settings(
                language=str(self.language_choice.currentData()),
                task=str(self.task_choice.currentData()),
                cpu_preset=str(self.cpu_choice.currentData()),
                batched_inference=self.batched_choice.isChecked(),
                batch_size=self.batch_size_choice.value(),
                vad_filter=self.vad_choice.isChecked(),
                beam_size=self.beam_choice.value(),
            )
            self._show_info(
                "Pengaturan transkripsi tersimpan. Berlaku saat worker berikutnya dimulai; "
                "file yang sudah selesai tidak diproses ulang."
            )
        except ValueError as exc:
            self._show_error(exc)

    def _save_export_settings(self) -> None:
        service = self._require_service()
        if service is None:
            return
        try:
            service.save_export_settings(
                markdown_individual=self.export_individual_choice.isChecked(),
                include_generated_at=self.export_generated_at_choice.isChecked(),
            )
            self._show_info("Pengaturan ekspor tersimpan. Klik Buat Hasil untuk menerapkannya.")
        except ValueError as exc:
            self._show_error(exc)

    def _clear_direct_roots(self) -> None:
        service = self._require_service()
        if service is None:
            return
        confirmed = QMessageBox.question(
            self,
            APP_NAME,
            "Keluarkan folder batch langsung dari cakupan?\n\n"
            "Tidak ada file audio yang dihapus. Transkrip yang sudah ada tetap tersimpan, "
            "tetapi file di folder itu tidak lagi dihitung di Beranda.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        service.clear_direct_roots()
        self._load_settings_fields()
        self.refresh()

    def _open_data_root(self) -> None:
        if self.paths is None:
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.root))):
            self._show_error(RuntimeError("Folder data tidak dapat dibuka."))

    def _refresh_transcript_table(self) -> None:
        if self.service is None:
            return
        state = self.state_filter.currentData()
        page = self.service.transcript_page(
            limit=self.page_size,
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
        page = self.service.review_page(limit=self.page_size, offset=self._review_offset)
        self._populate_table(self.review_table, page.rows)
        self._set_page_controls(
            total=page.total,
            offset=self._review_offset,
            label=self.review_page_label,
            previous=self.review_previous_button,
            next_button=self.review_next_button,
        )

    def _populate_table(self, table: QTableWidget, rows: list[Any]) -> None:
        """Rebuild a table without stealing the user's selection or scroll position.

        A periodic refresh that silently dropped the selection made "Hapus
        Riwayat Terpilih" impossible to click in time, so identical data is now
        left untouched and a real change restores both selection and scroll.
        """
        rendered = [
            (
                int(row["id"]),
                (
                    str(row["current_state"]),
                    str(row["sender"] or S.UNKNOWN_SENDER),
                    str(row["chat"] or "-"),
                    str(row["whatsapp_message_at"] or S.UNKNOWN_WHATSAPP_TIME),
                    str(row["basename"]),
                    str(row["duration_seconds"] or "-"),
                    str(row["model_name"] or "-"),
                    str(row["quality_status"] or "-"),
                    str(row["last_processed_at"] or "-"),
                ),
            )
            for row in rows
        ]
        fingerprint = tuple(rendered)
        if self._table_fingerprints.get(id(table)) == fingerprint:
            return
        self._table_fingerprints[id(table)] = fingerprint

        selected_ids = self._selected_ids_in(table)
        scrollbar = table.verticalScrollBar()
        scroll_position = scrollbar.value() if scrollbar is not None else 0
        table.setUpdatesEnabled(False)
        blocker = QSignalBlocker(table)
        try:
            table.clearSelection()
            table.setRowCount(len(rendered))
            for index, (audio_id, values) in enumerate(rendered):
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, audio_id)
                    table.setItem(index, column, item)
        finally:
            del blocker
            table.setUpdatesEnabled(True)
        self._restore_selection(table, selected_ids)
        if scrollbar is not None:
            scrollbar.setValue(scroll_position)
        if table is self.table:
            self._update_history_action_state()

    @staticmethod
    def _selected_ids_in(table: QTableWidget) -> set[int]:
        model = table.selectionModel()
        if model is None:
            return set()
        ids: set[int] = set()
        for index in model.selectedRows():
            anchor = table.item(index.row(), 0)
            if anchor is not None:
                value = anchor.data(Qt.ItemDataRole.UserRole)
                if isinstance(value, int):
                    ids.add(value)
        return ids

    @staticmethod
    def _restore_selection(table: QTableWidget, selected_ids: set[int]) -> None:
        """Reselect rows the user had chosen, skipping any that no longer exist."""
        if not selected_ids:
            return
        selection_model = table.selectionModel()
        model = table.model()
        if selection_model is None or model is None:
            return
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        for row_index in range(table.rowCount()):
            anchor = table.item(row_index, 0)
            if anchor is None:
                continue
            value = anchor.data(Qt.ItemDataRole.UserRole)
            if isinstance(value, int) and value in selected_ids:
                selection_model.select(model.index(row_index, 0), flags)

    def _selected_audio_ids(self) -> list[int]:
        return sorted(self._selected_ids_in(self.table))

    def _update_history_action_state(self) -> None:
        if hasattr(self, "delete_history_button"):
            self.delete_history_button.setEnabled(bool(self._selected_audio_ids()))

    def _clear_selected_history(self) -> None:
        service = self._require_service()
        if service is None:
            return
        audio_ids = self._selected_audio_ids()
        if not audio_ids:
            return
        count = len(audio_ids)
        confirmed = QMessageBox.question(
            self,
            APP_NAME,
            f"Hapus riwayat transkripsi untuk {count} file terpilih?\n\n"
            "Yang dihapus: transkrip, attempt, dan koreksi manual.\n"
            "Yang tetap aman: file audio sumber, lokasi folder, fingerprint, dan metadata chat.\n\n"
            "File tidak akan masuk antrean otomatis; pilih lagi saat ingin mentranskripsinya.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            removed = service.clear_transcript_history(audio_ids)
            self._show_info(f"Riwayat dihapus untuk {removed} file. Audio sumber tidak diubah.")
            self.refresh()
        except (RuntimeError, ValueError) as exc:
            self._show_error(exc)

    def _set_page_controls(
        self, *, total: int, offset: int, label: QLabel, previous: QPushButton, next_button: QPushButton
    ) -> None:
        page_size = self.page_size
        first = 0 if total == 0 else offset + 1
        last = min(total, offset + page_size)
        label.setText(f"Menampilkan {first}-{last} dari {total}")
        previous.setEnabled(offset > 0)
        next_button.setEnabled(offset + page_size < total)

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
        status = (
            None if self.paths is None else worker_status.read_status(self.paths.worker_status_file)
        )
        if status is None:
            self._worker_active = False
            self.worker_label.setText("Worker tidak aktif")
            self.worker_progress.setValue(0)
            return
        self._worker_active = worker_status.is_live(status)
        self.worker_label.setText(worker_status.status_text(status))
        self.worker_progress.setValue(worker_status.progress_percent(status))
        if str(status.get("state")) == "finished" and self.service is not None:
            session = status.get("session")
            session_key = (
                str(session.get("started_at"))
                if isinstance(session, dict) and session.get("started_at")
                else "finished"
            )
            if session_key not in self._previewed_finished_sessions:
                self._previewed_finished_sessions.add(session_key)
                QTimer.singleShot(0, self._show_transcript_preview)

    def _run_background(
        self,
        label: str,
        operation: Callable[[], object],
        succeeded: Callable[[object], None],
    ) -> None:
        """Run a use case that reports nothing until it finishes."""
        self._run_background_with_progress(label, lambda _job: operation(), succeeded)

    def _run_background_with_progress(
        self,
        label: str,
        operation: Callable[[ServiceJob], object],
        succeeded: Callable[[object], None],
        *,
        progress_label: str | None = None,
    ) -> None:
        self.operation_label.setText(label)
        job = ServiceJob(operation, self)
        self._jobs.add(job)
        if progress_label is not None:
            job.progressed.connect(
                lambda done, total: self.operation_label.setText(
                    f"{progress_label} {done}/{total}" if total else progress_label
                )
            )

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
            message = (
                f"Scan selesai: {summary.discovered} file baru, {summary.unchanged} tidak berubah."
            )
            if summary.source_changed:
                message += f" {summary.source_changed} sumber berubah."
            if summary.unreadable:
                message += f" {summary.unreadable} tidak dapat dibaca."
            if summary.missing:
                message += f" {summary.missing} tidak ditemukan lagi."
            self._show_info(message)

        self._run_background_with_progress(
            "Memindai folder audio…",
            lambda job: service.scan_audio(progress=job.report),
            complete,
            progress_label="Memindai file",
        )

    def _choose_audio_files(self) -> None:
        """Offer the keyboard-equivalent path for the drag-and-drop zone."""
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            "Pilih File Audio",
            "",
            "Audio yang didukung (*.opus *.ogg *.mp3 *.wav *.m4a *.aac *.flac *.webm *.mp4)",
        )
        if selected:
            self._add_audio_files([Path(path) for path in selected])

    def _add_audio_files(self, files: list[Path]) -> None:
        """Register an explicit, read-only batch then leave selection visible in preflight."""
        service = self._require_service()
        if service is None or not files:
            return

        def complete(result: object) -> None:
            if not isinstance(result, DirectFileBatchSummary):
                return
            self._show_info(
                f"{result.selected_count} file ditambahkan dari {result.source_count} pilihan. "
                f"Scan menemukan {result.scan.discovered} file baru. "
                "Klik Siapkan & Mulai Transkripsi untuk memilih model dan cakupan. "
                "Belum ada audio yang diproses."
            )

        self._run_background(
            "Menambahkan file audio tanpa memindahkan sumber…",
            lambda: service.add_audio_files(files),
            complete,
        )

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
        dialog = ExportSetupDialog(service.default_export_name(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def complete(result: object) -> None:
            if not isinstance(result, ExportResult):
                return
            self._last_export_dir = result.output_dir
            self.open_last_export_button.setEnabled(True)
            self.output_path_label.setText(f"Hasil terakhir: {result.output_dir}")
            self._open_last_export(show_error=False)
            self._show_info(
                f"Hasil dibuat untuk {result.records} transkrip. Folder hasil spesifik dibuka otomatis.\n\n"
                f"{result.output_dir}"
            )

        self._run_background(
            "Membuat hasil dari database lokal…",
            lambda: service.export_selected(
                name=dialog.name_input.text(),
                formats=dialog.formats(),
                include_individual=dialog.individual.isChecked(),
            ),
            complete,
        )

    def _show_transcript_preview(self) -> None:
        service = self._require_service()
        if service is None:
            return
        try:
            entries = service.transcript_preview()
        except ValueError as exc:
            self._show_error(exc)
            return
        if not entries:
            self._show_info("Belum ada hasil transkripsi untuk dipreview.")
            return
        TranscriptPreviewDialog(entries, self).exec()

    def _open_last_export(self, *, show_error: bool = True) -> bool:
        if self._last_export_dir is None:
            if show_error:
                QMessageBox.warning(self, APP_NAME, "Belum ada hasil ekspor khusus pada sesi ini.")  # type: ignore[call-arg]
            return False
        self._last_export_dir.mkdir(parents=True, exist_ok=True)
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_export_dir)))
        if not opened and show_error:
            QMessageBox.warning(self, APP_NAME, "Folder hasil terakhir tidak dapat dibuka.")  # type: ignore[call-arg]
        return opened

    def _open_output(self, *, show_error: bool = True) -> bool:
        """Open only the app-owned derived-output directory in Windows Explorer."""
        if self.paths is None:
            if show_error:
                QMessageBox.warning(self, APP_NAME, "Folder hasil belum tersedia.")  # type: ignore[call-arg]
            return False
        self.paths.output_dir.mkdir(parents=True, exist_ok=True)
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.output_dir)))
        if not opened and show_error:
            QMessageBox.warning(self, APP_NAME, "Folder hasil tidak dapat dibuka.")  # type: ignore[call-arg]
        return opened

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
        keys = list(MODELS)
        key, accepted = QInputDialog.getItem(self, APP_NAME, "Pilih model default", keys, 0, False)
        if not accepted:
            return
        try:
            service.set_default_model(key)
            self._show_info(f"Model default diubah menjadi {key}. File yang sudah selesai tidak diproses ulang.")
            self.refresh()
        except Exception as exc:
            self._show_error(exc)

    def _model_key(self, title: str) -> str | None:
        key, accepted = QInputDialog.getItem(self, APP_NAME, title, list(MODELS), 0, False)
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

    def _queue_search_refresh(self, _: object = None) -> None:
        """Coalesce keystrokes so one query runs per pause, not per character."""
        self._search_debounce.start()

    def _reset_paging(self, _: object = None) -> None:
        self._page_offset = 0
        self.refresh()

    def _previous_page(self) -> None:
        self._page_offset = max(0, self._page_offset - self.page_size)
        self.refresh()

    def _next_page(self) -> None:
        self._page_offset += self.page_size
        self.refresh()

    def _previous_review_page(self) -> None:
        self._review_offset = max(0, self._review_offset - self.page_size)
        self.refresh()

    def _next_review_page(self) -> None:
        self._review_offset += self.page_size
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


def _select_data(combo: QComboBox, value: object) -> None:
    """Select the entry carrying `value`, leaving the box untouched if absent."""
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


def run_ui(data_dir: Path | None = None, self_test: bool = False) -> int:
    paths = DataPaths(root=data_dir or default_data_root())
    first_run = not paths.config_file.exists()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    install_brand_fonts()
    app.setWindowIcon(brand_icon())
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
