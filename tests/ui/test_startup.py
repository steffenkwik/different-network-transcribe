"""Phase 1 gate: the application opens with an empty database and does not crash."""

from __future__ import annotations

import wave
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt

from app.paths import DataPaths

pytestmark = [pytest.mark.ui]


def _write_silent_wav(path: Path, *, frames: int = 800) -> None:
    """Create a tiny decodable fixture without using any private audio."""
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8_000)
        stream.writeframes(b"\x00\x00" * frames)


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


def _service_with_rows(tmp_path: Path, count: int = 3):
    from app.services.application_service import ApplicationService

    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    source = tmp_path / "source"
    source.mkdir()
    for index in range(count):
        (source / f"voice-{index}.opus").write_bytes(f"voice-{index}".encode())
    service.save_audio_root(source)
    service.scan_audio()
    return paths, service


def test_periodic_refresh_keeps_the_users_row_selection(qtbot, tmp_path: Path) -> None:
    """P0-2 regression: the 750 ms tick cleared the selection, so the delete
    button could never stay enabled long enough to be clicked."""
    from app.ui.launch import MainWindow

    paths, service = _service_with_rows(tmp_path)
    window = MainWindow(paths=paths, service=service)
    qtbot.addWidget(window)
    window.refresh()
    assert window.table.rowCount() == 3

    window.table.selectRow(1)
    selected = window._selected_audio_ids()
    assert len(selected) == 1
    assert window.delete_history_button.isEnabled()

    window.refresh()
    window.refresh()

    assert window._selected_audio_ids() == selected
    assert window.delete_history_button.isEnabled()


def test_refresh_never_overwrites_a_folder_path_being_typed(qtbot, tmp_path: Path) -> None:
    """P0-2 regression: refresh rewrote the settings fields on every tick."""
    from app.ui.launch import MainWindow

    paths, service = _service_with_rows(tmp_path, count=1)
    window = MainWindow(paths=paths, service=service)
    qtbot.addWidget(window)
    window.pages.setCurrentIndex(MainWindow.SETTINGS_PAGE_INDEX)
    assert window.audio_root.text() == str((tmp_path / "source").resolve())

    window.audio_root.setText(r"D:\sedang diketik pengguna")
    window.refresh()
    window._tick()

    assert window.audio_root.text() == r"D:\sedang diketik pengguna"


def test_leaving_and_reentering_settings_reloads_the_saved_paths(qtbot, tmp_path: Path) -> None:
    from app.ui.launch import MainWindow

    paths, service = _service_with_rows(tmp_path, count=1)
    window = MainWindow(paths=paths, service=service)
    qtbot.addWidget(window)
    window.pages.setCurrentIndex(MainWindow.SETTINGS_PAGE_INDEX)
    window.audio_root.setText("teks yang dibuang")
    window.pages.setCurrentIndex(0)
    window.pages.setCurrentIndex(MainWindow.SETTINGS_PAGE_INDEX)

    assert window.audio_root.text() == str((tmp_path / "source").resolve())


def test_search_typing_is_debounced_into_a_single_refresh(qtbot, tmp_path: Path) -> None:
    """P0-2 regression: every keystroke ran the full paged query immediately."""
    from app.ui.launch import MainWindow

    paths, service = _service_with_rows(tmp_path, count=1)
    window = MainWindow(paths=paths, service=service)
    qtbot.addWidget(window)
    calls: list[int] = []
    window._reset_paging = lambda *_: calls.append(1)  # type: ignore[method-assign]
    window._search_debounce.timeout.disconnect()
    window._search_debounce.timeout.connect(window._reset_paging)

    for character in "halo":
        window.search_input.setText(window.search_input.text() + character)

    assert calls == []  # nothing ran while the user was still typing
    qtbot.wait(MainWindow.SEARCH_DEBOUNCE_MS + 250)
    assert calls == [1]


def test_dashboard_breakdown_line_accounts_for_every_row(qtbot, tmp_path: Path) -> None:
    """P0-3 regression: excluded and no-speech rows were missing from the cards."""
    from app.ui.launch import MainWindow

    paths, service = _service_with_rows(tmp_path, count=2)
    window = MainWindow(paths=paths, service=service)
    qtbot.addWidget(window)
    window.refresh()

    assert "Rincian Total VN" in window.metric_breakdown.text()
    assert "dikecualikan" in window.metric_breakdown.text()
    assert "tanpa suara" in window.metric_breakdown.text()


def test_progress_bar_ignores_all_time_counts_from_a_status_file(qtbot, tmp_path: Path) -> None:
    """P0-3 regression: a fresh session used to open at 96% on an old archive."""
    import json

    from app.ui.launch import MainWindow

    paths, service = _service_with_rows(tmp_path, count=1)
    window = MainWindow(paths=paths, service=service)
    qtbot.addWidget(window)
    paths.worker_status_file.parent.mkdir(parents=True, exist_ok=True)
    paths.worker_status_file.write_text(
        json.dumps(
            {
                "schema": 2,
                "state": "running",
                "session": {"total": 20, "done": 1, "failed": 0, "current_file": "voice-2.opus"},
                "counts": {"queued": 19, "completed": 500, "failed": 0},
            }
        ),
        encoding="utf-8",
    )

    window._refresh_worker_status()

    assert window.worker_progress.value() == 5
    assert "1/20 file" in window.worker_label.text()


def test_settings_controls_are_loaded_from_config_and_take_effect(qtbot, tmp_path: Path) -> None:
    """Phase 3: a control that does not do what it says is worse than a missing one."""
    from app.ui.launch import MainWindow

    paths, service = _service_with_rows(tmp_path, count=1)
    window = MainWindow(paths=paths, service=service)
    qtbot.addWidget(window)
    window.pages.setCurrentIndex(MainWindow.SETTINGS_PAGE_INDEX)

    # Defaults arrive from config, not from hard-coded widget state.
    assert window.language_choice.currentData() == "id"
    assert window.task_choice.currentData() == "transcribe"
    assert window.batched_choice.isChecked() is True

    window.language_choice.setCurrentIndex(window.language_choice.findData("auto"))
    window.task_choice.setCurrentIndex(window.task_choice.findData("translate"))
    window.cpu_choice.setCurrentIndex(window.cpu_choice.findData("maksimal"))
    window.batched_choice.setChecked(False)
    window.batch_size_choice.setValue(12)
    window.vad_choice.setChecked(False)
    window.beam_choice.setValue(2)
    with patch.object(MainWindow, "_show_info"):
        window._save_transcription_settings()

    # Reaches the config the worker actually reads on its next start.
    saved = service.transcription_settings()
    assert saved.language == "auto"
    assert saved.task == "translate"
    assert saved.cpu_preset == "maksimal"
    assert saved.batched_inference is False
    assert saved.batch_size == 12
    assert saved.vad_filter is False
    assert saved.beam_size == 2


def test_ui_page_size_and_poll_interval_come_from_config(qtbot, tmp_path: Path) -> None:
    """Both were validated by config and read by nothing."""
    from app import config as config_mod
    from app.ui.launch import MainWindow

    paths, service = _service_with_rows(tmp_path, count=12)
    config = config_mod.load(paths.config_file, paths.config_lastgood_file)
    config.ui.page_size = 10
    config.ui.poll_interval_ms = 900
    config_mod.save(config, paths.config_file, paths.config_lastgood_file)

    window = MainWindow(paths=paths, service=service)
    qtbot.addWidget(window)
    window.refresh()

    assert window.page_size == 10
    assert window._worker_status_timer.interval() == 900
    assert window.table.rowCount() == 10
    assert "1-10 dari 12" in window.page_label.text()
    window._next_page()
    assert "11-12 dari 12" in window.page_label.text()


def test_cpu_preset_shows_the_real_thread_count(qtbot, tmp_path: Path) -> None:
    """The preset used to be a name with no consequence anywhere."""
    from app.ui.launch import MainWindow

    paths, service = _service_with_rows(tmp_path, count=1)
    window = MainWindow(paths=paths, service=service)
    qtbot.addWidget(window)
    window.pages.setCurrentIndex(MainWindow.SETTINGS_PAGE_INDEX)

    window.cpu_choice.setCurrentIndex(window.cpu_choice.findData("rendah"))
    low = window.cpu_threads_label.text()
    window.cpu_choice.setCurrentIndex(window.cpu_choice.findData("maksimal"))
    high = window.cpu_threads_label.text()

    assert "thread" in low
    assert low != high
    with patch.object(MainWindow, "_show_info"):
        window._save_transcription_settings()
    assert service.resolved_cpu_threads() >= 1


def test_export_options_are_loaded_and_saved(qtbot, tmp_path: Path) -> None:
    from app.ui.launch import MainWindow

    paths, service = _service_with_rows(tmp_path, count=1)
    window = MainWindow(paths=paths, service=service)
    qtbot.addWidget(window)
    window.pages.setCurrentIndex(MainWindow.SETTINGS_PAGE_INDEX)

    assert window.export_individual_choice.isChecked() is False
    window.export_individual_choice.setChecked(True)
    window.export_generated_at_choice.setChecked(True)
    with patch.object(MainWindow, "_show_info"):
        window._save_export_settings()

    saved = service.export_settings()
    assert saved.markdown_individual is True
    assert saved.include_generated_at is True


def test_direct_roots_are_visible_and_clearable(qtbot, tmp_path: Path) -> None:
    from app.ui.launch import MainWindow

    paths, service = _service_with_rows(tmp_path, count=1)
    picked_dir = tmp_path / "downloads"
    picked_dir.mkdir()
    picked = picked_dir / "picked.wav"
    _write_silent_wav(picked)
    service.add_audio_files([picked])

    window = MainWindow(paths=paths, service=service)
    qtbot.addWidget(window)
    window.pages.setCurrentIndex(MainWindow.SETTINGS_PAGE_INDEX)
    assert "downloads" in window.direct_roots_label.text()

    with patch("app.ui.launch.QMessageBox.question", return_value=Qt_Yes()):
        window._clear_direct_roots()

    assert service.configured_direct_roots() == []
    assert "Belum ada" in window.direct_roots_label.text()


def Qt_Yes():
    from PySide6.QtWidgets import QMessageBox

    return QMessageBox.StandardButton.Yes


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
    assert "turbo" in dialog.model_buttons
    assert dialog.start_button.isEnabled() is False


def _preflight_with_candidates(tmp_path: Path, count: int):
    """Install a fake verified model so the preflight has something selectable."""
    from app.services.application_service import ApplicationService
    from app.transcription.model_registry import MODELS, ModelRegistry

    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    model_dir = paths.models_dir / "small"
    model_dir.mkdir(parents=True)
    for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.json"):
        (model_dir / name).write_bytes(b"fake-but-present")
    ModelRegistry(paths.models_dir)._write_registry(
        MODELS["small"], {"model.bin": {"size": 16, "sha256": "abc"}}, "download"
    )
    source = tmp_path / "source"
    source.mkdir()
    for index in range(count):
        # Real, decodable audio with a distinct length per file, so each keeps
        # its own SHA-256 identity and survives as a queue candidate.
        _write_silent_wav(source / f"voice-{index:05d}.wav", frames=800 + index)
    service.save_audio_root(source)
    service.scan_audio()
    return paths, service


def test_preflight_can_select_thousands_without_a_twenty_file_cap(qtbot, tmp_path: Path) -> None:
    """P1-1 regression: the old dialog refused to start more than 20 files."""
    from app.ui.launch import TranscriptionSetupDialog

    _, service = _preflight_with_candidates(tmp_path, 600)
    dialog = TranscriptionSetupDialog(service)
    qtbot.addWidget(dialog)

    assert dialog.scope() == TranscriptionSetupDialog.SCOPE_ALL
    assert dialog.planned_count() == 600
    # A batch this size must be confirmed, but it must not be forbidden.
    assert dialog.confirm_large.isVisible() is False or not dialog.start_button.isEnabled()
    assert dialog.start_button.isEnabled() is False
    dialog.confirm_large.setChecked(True)
    assert dialog.start_button.isEnabled() is True


def test_preflight_only_pages_the_table_not_the_whole_archive(qtbot, tmp_path: Path) -> None:
    from app.ui.launch import TranscriptionSetupDialog

    _, service = _preflight_with_candidates(tmp_path, 600)
    dialog = TranscriptionSetupDialog(service)
    qtbot.addWidget(dialog)

    # 600 candidates must never become 600 widgets.
    assert dialog.file_table.rowCount() == TranscriptionSetupDialog.PAGE_SIZE
    assert "1-250 dari 600" in dialog.file_help.text()
    dialog._next_page()
    assert "251-500 dari 600" in dialog.file_help.text()


def test_preflight_ticks_survive_paging(qtbot, tmp_path: Path) -> None:
    from app.ui.launch import TranscriptionSetupDialog

    _, service = _preflight_with_candidates(tmp_path, 600)
    dialog = TranscriptionSetupDialog(service)
    qtbot.addWidget(dialog)
    dialog.scope_selected.setChecked(True)
    dialog._scope_changed()

    dialog._check_visible(True)
    assert dialog.planned_count() == 250
    dialog._next_page()
    dialog._check_visible(True)
    assert dialog.planned_count() == 500
    dialog._previous_page()
    # Returning to page one must show the ticks that are still in effect.
    assert dialog.file_table.item(0, 0).checkState() == Qt.CheckState.Checked
    assert dialog.planned_count() == 500


def test_preflight_starts_a_small_batch_without_extra_confirmation(qtbot, tmp_path: Path) -> None:
    from app.ui.launch import TranscriptionSetupDialog

    _, service = _preflight_with_candidates(tmp_path, 5)
    dialog = TranscriptionSetupDialog(service)
    qtbot.addWidget(dialog)

    assert dialog.planned_count() == 5
    assert dialog.confirm_large.isVisible() is False
    assert dialog.start_button.isEnabled() is True


def test_preflight_commits_the_chosen_scope(qtbot, tmp_path: Path) -> None:
    from app.ui.launch import TranscriptionSetupDialog

    _, service = _preflight_with_candidates(tmp_path, 8)
    dialog = TranscriptionSetupDialog(service)
    qtbot.addWidget(dialog)
    dialog.scope_selected.setChecked(True)
    dialog._scope_changed()
    dialog._check_visible(True)
    for row in range(4):
        dialog.file_table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)

    assert dialog.planned_count() == 4
    dialog._commit_and_accept()

    # Unticked rows stay listed so they can be re-selected later, but only the
    # ticked ones are enabled, so only they can enter the queue.
    page = service.transcription_candidates(limit=50)
    assert page.total == 8
    assert sum(1 for row in page.rows if row["transcription_enabled"]) == 4
    assert {str(row["current_state"]) for row in page.rows if not row["transcription_enabled"]} == {
        "excluded"
    }
