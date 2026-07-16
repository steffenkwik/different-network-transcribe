"""Model registry tests use tiny dummy artifacts and never contact Hugging Face."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.transcription.model_registry import MODELS, ModelError, ModelRegistry

pytestmark = [pytest.mark.unit]


def _write_artifacts(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
        (folder / name).write_text(name, encoding="utf-8")


def test_explicit_download_verifies_then_promotes_atomically(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path / "Models")
    installed = registry.install_from_hub(
        "small", lambda _, destination: _write_artifacts(destination)
    )
    assert installed == tmp_path / "Models" / "small"
    assert registry.verify("small")["model.bin"]["size"] > 0
    assert registry.read()["models"]["small"]["verification_state"] == "verified"


def test_failed_download_preserves_no_partial_or_invalid_final(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path / "Models")
    with pytest.raises(ModelError):
        registry.install_from_hub(
            "small", lambda _, destination: (destination / "model.bin").write_text("x")
        )
    assert not (tmp_path / "Models" / "small").exists()
    assert not list((tmp_path / "Models" / ".partial").glob("*"))


def test_offline_import_rejects_zip_slip(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("../escape.txt", "no")
    with pytest.raises(ModelError, match="tidak aman"):
        ModelRegistry(tmp_path / "Models").import_zip("small", archive)


def test_offline_import_accepts_verified_pack(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write_artifacts(source)
    archive = tmp_path / "small.zip"
    with zipfile.ZipFile(archive, "w") as package:
        for path in source.iterdir():
            package.write(path, path.name)
    installed = ModelRegistry(tmp_path / "Models").import_zip("small", archive)
    assert (installed / "model.bin").read_text(encoding="utf-8") == "model.bin"


def test_high_model_is_an_explicit_local_accuracy_option() -> None:
    high = MODELS["high"]
    assert high.hf_repo == "Systran/faster-whisper-large-v3"
    assert high.expected_size_bytes > MODELS["medium"].expected_size_bytes
    assert high.minimum_ram_bytes > MODELS["medium"].minimum_ram_bytes
