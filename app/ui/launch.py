"""UI process bootstrap.

Phase 1 scope: start Qt, load config, set up logging, show an empty main window.
The four navigation sections and the first-run wizard arrive in Phase 9; this
module's job is to own the startup sequence so later phases only add to it.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

from app import config as config_mod
from app.logging_setup import new_session_id, setup_logging
from app.paths import DataPaths, default_data_root
from app.resources import strings_id as S
from app.version import APP_NAME, APP_VERSION


class MainWindow(QMainWindow):
    """Empty shell. Phase 9 replaces the placeholder with the four sections."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 720)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(QLabel(f"{APP_NAME} {APP_VERSION}"))
        layout.addWidget(QLabel(S.WIZARD_WELCOME))
        layout.addStretch(1)
        self.setCentralWidget(central)


def run_ui(data_dir: Path | None = None, self_test: bool = False) -> int:
    paths = DataPaths(root=data_dir or default_data_root())
    paths.ensure()

    cfg = config_mod.load(paths.config_file, paths.config_lastgood_file)

    session_id = new_session_id()
    setup_logging(
        paths.logs_dir,
        session_id=session_id,
        role="ui",
        level=cfg.diagnostics.log_level,
        allow_transcript_bodies=cfg.privacy.log_transcript_bodies,
        keep_days=cfg.diagnostics.keep_log_days,
    )
    log = logging.getLogger("ui")
    log.info(
        "ui starting",
        extra={"app_version": APP_VERSION, "data_root": str(paths.root)},
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    window = MainWindow()
    window.show()

    if self_test:
        return _run_self_test(app, window, log)

    return app.exec()


def _run_self_test(app: QApplication, window: MainWindow, log: logging.Logger) -> int:
    """Prove the window really rendered, then exit.

    Used by the Phase 11 packaging gate to smoke-test the installed build and the
    portable ZIP on a machine with no system Python. Exit code 0 means the GUI
    came up; the printed line is what the build script asserts on.
    """
    result: dict[str, object] = {}

    def check() -> None:
        result["visible"] = window.isVisible()
        result["title"] = window.windowTitle()
        result["platform"] = QApplication.platformName()
        app.quit()

    QTimer.singleShot(1500, check)
    app.exec()

    ok = bool(result.get("visible")) and result.get("title") == APP_NAME
    log.info("self-test finished", extra={"ok": ok, **result})
    print(
        f"SELF_TEST {'PASS' if ok else 'FAIL'} "
        f"visible={result.get('visible')} "
        f"title={result.get('title')!r} "
        f"platform={result.get('platform')!r} "
        f"version={APP_VERSION}"
    )
    return 0 if ok else 1
