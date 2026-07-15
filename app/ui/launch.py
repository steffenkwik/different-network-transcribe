"""PySide6 presentation layer: Indonesian navigation and first-run wizard only."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from app import config as config_mod
from app.logging_setup import new_session_id, setup_logging
from app.paths import DataPaths, default_data_root
from app.resources import strings_id as S
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
    def __init__(self, paths: DataPaths | None = None) -> None:
        super().__init__()
        self.paths = paths
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

    def _home(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(f"{APP_NAME} {APP_VERSION}"))
        layout.addWidget(
            QLabel(
                "Total VN: 0    Selesai: 0    Belum Diproses: 0    Perlu Diperiksa: 0    Gagal: 0"
            )
        )
        for label in (
            S.ACTION_SCAN,
            S.ACTION_TEST_20,
            S.ACTION_START,
            S.ACTION_PAUSE,
            S.ACTION_SAFE_STOP,
            S.ACTION_EXPORT,
            S.ACTION_OPEN_OUTPUT,
        ):
            layout.addWidget(QPushButton(label))
        layout.addStretch(1)
        return page

    def _all(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(S.NAV_ALL))
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
        layout.addWidget(table)
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
        layout.addWidget(QPushButton("Unduh/Impor Model"))
        layout.addWidget(QPushButton("Backup Sekarang"))
        layout.addWidget(QPushButton("Pulihkan Paket"))
        layout.addStretch(1)
        return page


def run_ui(data_dir: Path | None = None, self_test: bool = False) -> int:
    paths = DataPaths(root=data_dir or default_data_root())
    paths.ensure()
    cfg = config_mod.load(paths.config_file, paths.config_lastgood_file)
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
    window = MainWindow(paths)
    window.show()
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
