"""Config validation, last-known-good fallback, and unknown-field preservation
(addendum section 15)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import config as config_mod
from app.config import AppConfig, ConfigError, resolve_cpu_threads

pytestmark = pytest.mark.unit


def test_defaults_match_blueprint() -> None:
    """Blueprint section 7.2 pins these exactly. They feed the compatibility key."""
    t = AppConfig().transcription
    assert t.default_model == "small"
    assert t.review_model == "medium"
    assert t.language == "id"
    assert t.task == "transcribe"
    assert t.device == "cpu"
    assert t.compute_type == "int8"
    assert t.beam_size == 5
    assert t.temperature == 0.0
    assert t.vad_filter is True
    assert t.condition_on_previous_text is False
    assert t.workers == 1


def test_privacy_defaults_are_off() -> None:
    p = AppConfig().privacy
    assert p.telemetry is False
    assert p.analytics is False
    assert p.crash_upload is False
    assert p.log_transcript_bodies is False


def test_privacy_cannot_be_switched_on() -> None:
    """A config file must not be able to turn this into a data-sending product."""
    cfg = AppConfig()
    cfg.privacy.telemetry = True
    with pytest.raises(ConfigError):
        cfg.validate()


def test_translate_is_an_allowed_explicit_task_but_never_the_default() -> None:
    """Whisper's translate mode runs locally, so the old ban was scope, not privacy.

    It stays opt-in: the default is always plain transcription.
    """
    assert AppConfig().transcription.task == "transcribe"
    cfg = AppConfig()
    cfg.transcription.task = "translate"
    cfg.validate()


def test_unknown_task_is_still_rejected() -> None:
    cfg = AppConfig()
    cfg.transcription.task = "summarise"
    with pytest.raises(ConfigError):
        cfg.validate()


def test_optional_thread_override_survives_a_save_load_cycle(tmp_path: Path) -> None:
    """Regression: None was written as "", so the first caller of
    resolved_threads() crashed with a string/int comparison."""
    config_file = tmp_path / "config.toml"
    lastgood = tmp_path / "config.lastgood.toml"
    config_mod.save(AppConfig(), config_file, lastgood)

    loaded = config_mod.load(config_file, lastgood)

    assert loaded.transcription.cpu_threads_override is None
    assert loaded.transcription.resolved_threads() >= 1


def test_thread_override_written_as_empty_string_by_an_older_build_is_tolerated(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'schema_version = 1\n[transcription]\ncpu_threads_override = ""\n', encoding="utf-8"
    )

    loaded = config_mod.load(config_file, None)

    assert loaded.transcription.cpu_threads_override is None
    assert loaded.transcription.resolved_threads() >= 1


def test_explicit_thread_override_is_honoured(tmp_path: Path) -> None:
    cfg = AppConfig()
    cfg.transcription.cpu_threads_override = 3
    config_file = tmp_path / "config.toml"
    config_mod.save(cfg, config_file, None)

    assert config_mod.load(config_file, None).transcription.resolved_threads() == 3


@pytest.mark.parametrize(
    ("preset", "logical", "expected"),
    [
        ("rendah", 16, 6),
        ("seimbang", 16, 11),
        ("maksimal", 16, 14),
        ("seimbang", 4, 3),
        ("rendah", 1, 1),  # never zero threads
    ],
)
def test_cpu_presets_derive_from_the_machine(preset: str, logical: int, expected: int) -> None:
    """Blueprint 7.2: 'Do not hardcode the current user's CPU.'"""
    assert resolve_cpu_threads(preset, logical_cpus=logical) == expected


def test_roundtrip_save_load(tmp_path: Path) -> None:
    cfg = AppConfig()
    cfg.transcription.default_model = "medium"
    cfg.ui.theme = "dark"
    cfg.paths.audio_roots = [r"D:\some\folder"]

    config_file = tmp_path / "config.toml"
    lastgood = tmp_path / "config.lastgood.toml"
    config_mod.save(cfg, config_file, lastgood)

    loaded = config_mod.load(config_file, lastgood)
    assert loaded.transcription.default_model == "medium"
    assert loaded.ui.theme == "dark"
    assert loaded.paths.audio_roots == [r"D:\some\folder"]
    assert lastgood.exists()


def test_corrupt_config_falls_back_to_last_known_good(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    lastgood = tmp_path / "config.lastgood.toml"

    good = AppConfig()
    good.ui.theme = "dark"
    config_mod.save(good, config_file, lastgood)

    config_file.write_text("this is not valid toml [[[", encoding="utf-8")

    loaded = config_mod.load(config_file, lastgood)
    assert loaded.ui.theme == "dark", "must recover from the last-known-good copy"


def test_invalid_value_falls_back_rather_than_crashing(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    lastgood = tmp_path / "config.lastgood.toml"
    config_mod.save(AppConfig(), config_file, lastgood)

    config_file.write_text(
        'schema_version = 1\n[transcription]\nbeam_size = 999\n', encoding="utf-8"
    )
    loaded = config_mod.load(config_file, lastgood)
    assert loaded.transcription.beam_size == 5, "invalid config must not start the app"


def test_missing_config_uses_defaults(tmp_path: Path) -> None:
    loaded = config_mod.load(tmp_path / "absent.toml", tmp_path / "absent.lastgood.toml")
    assert loaded.transcription.default_model == "small"


def test_unknown_fields_are_preserved(tmp_path: Path) -> None:
    """Addendum 15.4: do not silently destroy a setting written by a newer version."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'schema_version = 1\n\n[future_feature]\nenabled = true\n', encoding="utf-8"
    )
    loaded = config_mod.load(config_file, None)
    config_mod.save(loaded, config_file, None)

    assert "future_feature" in config_file.read_text(encoding="utf-8")


def test_config_from_newer_schema_is_rejected() -> None:
    cfg = AppConfig(schema_version=99)
    with pytest.raises(ConfigError):
        cfg.validate()


def test_high_model_is_a_valid_explicit_choice() -> None:
    cfg = AppConfig()
    cfg.transcription.default_model = "high"
    cfg.transcription.review_model = "high"
    cfg.validate()
