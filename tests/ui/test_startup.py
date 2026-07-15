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
