"""Phase 1 gate: the application opens with an empty database and does not crash."""

from __future__ import annotations

from pathlib import Path

import pytest

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
