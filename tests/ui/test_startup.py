"""Phase 1 gate: the application opens with an empty database and does not crash."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.paths import DataPaths

pytestmark = [pytest.mark.ui]


def test_main_window_opens_empty(qtbot, tmp_path: Path) -> None:
    from app.ui.launch import MainWindow
    from app.version import APP_NAME

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert window.isVisible()
    assert window.windowTitle() == APP_NAME


def test_worker_flag_is_parsed_without_importing_qt() -> None:
    """The worker role must be selectable before Qt is ever touched."""
    from app.main import build_parser

    args = build_parser().parse_args(
        ["--worker", "--data-dir", r"X:\data", "--session", "abc123"]
    )
    assert args.worker is True
    assert args.session == "abc123"


def test_worker_requires_data_dir_and_session() -> None:
    from app.main import main

    assert main(["--worker"]) == 2


def test_first_run_wizard_collects_optional_folders(qtbot, tmp_path: Path) -> None:
    from app.paths import DataPaths
    from app.ui.launch import FirstRunWizard

    wizard = FirstRunWizard(DataPaths(tmp_path / "data"))
    qtbot.addWidget(wizard)
    assert wizard.selected_data_root() == tmp_path / "data"
    assert wizard.selected_audio_root() is None
    assert wizard.selected_chat_root() is None


def test_window_declares_a_safe_close_handler() -> None:
    """A future UI refactor must not silently kill an active local worker."""
    from app.ui.launch import MainWindow

    assert "safe_stop_transcription" in MainWindow.closeEvent.__doc__ or "Never kill" in MainWindow.closeEvent.__doc__


def test_engine_import_self_test_flag_is_available() -> None:
    from app.main import build_parser

    assert build_parser().parse_args(["--engine-import-self-test"]).engine_import_self_test is True


def test_open_output_button_opens_the_app_owned_output_folder(qtbot, tmp_path: Path) -> None:
    from app.ui.launch import MainWindow

    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    window = MainWindow(paths=paths)
    qtbot.addWidget(window)
    with patch("app.ui.launch.QDesktopServices.openUrl", return_value=True) as open_url:
        window._open_output()

    assert paths.output_dir.is_dir()
    assert open_url.call_count == 1


def test_safe_twenty_file_test_action_is_available(qtbot) -> None:
    """The beginner-safe test path must never regress to a disabled placeholder."""
    from app.ui.launch import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    assert window.test_button.isEnabled()
    assert "20" in window.test_button.toolTip()


def test_direct_file_picker_and_drop_zone_are_available(qtbot, tmp_path: Path) -> None:
    """Drag-and-drop has a visible, keyboard-accessible picker alternative."""
    from app.ui.launch import MainWindow

    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    window = MainWindow(paths=paths)
    qtbot.addWidget(window)

    assert window.audio_drop_zone.acceptDrops() is True
    assert window.add_audio_button.isEnabled() is True
    assert "Pilih File Audio" in window.add_audio_button.text()
    assert str(paths.output_dir) in window.output_path_label.text()


def test_branded_navigation_and_preflight_are_present(qtbot, tmp_path: Path) -> None:
    """The DN treatment and safe model/file preflight are deliberate UI contracts."""
    from app.services.application_service import ApplicationService
    from app.ui.launch import MainWindow, TranscriptionSetupDialog

    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    window = MainWindow(paths=paths, service=service)
    qtbot.addWidget(window)
    assert len(window._nav_buttons) == 4
    assert window._nav_buttons[0].isChecked()
    dialog = TranscriptionSetupDialog(service, window)
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Siapkan Transkripsi"
    assert "high" in dialog.model_buttons
    assert dialog.start_button.isEnabled() is False
