"""Explicit, verified local model installation and offline ZIP import."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ModelDefinition:
    key: str
    display_name: str
    hf_repo: str
    expected_size_bytes: int
    minimum_ram_bytes: int


MODELS = {
    "small": ModelDefinition(
        "small",
        "Small — Cepat, direkomendasikan",
        "Systran/faster-whisper-small",
        483_183_820,
        1_073_741_824,
    ),
    "medium": ModelDefinition(
        "medium",
        "Medium — Lebih akurat, lebih lambat",
        "Systran/faster-whisper-medium",
        1_527_000_000,
        2_684_354_560,
    ),
    "high": ModelDefinition(
        "high",
        "High — Paling akurat, paling lambat",
        "Systran/faster-whisper-large-v3",
        3_100_000_000,
        5_368_709_120,
    ),
}
# Systran's current Large-v3 release ships ``vocabulary.json``; older
# faster-whisper model folders used ``vocabulary.txt``.  Both formats are valid
# CTranslate2 Whisper assets, so requiring only the old filename made High look
# corrupt even after a correct download.
REQUIRED_FILES = frozenset({"config.json", "model.bin", "tokenizer.json"})
VOCABULARY_FILES = frozenset({"vocabulary.json", "vocabulary.txt"})
Downloader = Callable[[str, Path], None]


class ModelError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def missing_model_files(folder: Path) -> list[str]:
    """Return human-readable missing requirements for any supported model layout."""
    missing = [name for name in REQUIRED_FILES if not (folder / name).is_file()]
    if not any((folder / name).is_file() for name in VOCABULARY_FILES):
        missing.append("vocabulary.json atau vocabulary.txt")
    return sorted(missing)


class ModelRegistry:
    """A model install starts only when the caller explicitly invokes install/import."""

    def __init__(self, models_dir: Path) -> None:
        self.models_dir = models_dir
        self.registry_file = models_dir / "registry.json"

    def _partial_dir(self, key: str) -> Path:
        return self.models_dir / ".partial" / f"{key}-{uuid.uuid4().hex}"

    def _write_registry(
        self, model: ModelDefinition, manifest: dict[str, dict[str, Any]], source: str
    ) -> None:
        self.models_dir.mkdir(parents=True, exist_ok=True)
        current = self.read()
        current["models"][model.key] = {
            "display_name": model.display_name,
            "engine_model_id": model.key,
            "hf_repo": model.hf_repo,
            "local_folder": model.key,
            "expected_size_bytes": model.expected_size_bytes,
            "min_ram_recommendation_bytes": model.minimum_ram_bytes,
            "installed": True,
            "install_source": source,
            "installed_at": _now(),
            "verification_state": "verified",
            "last_verified_at": _now(),
            "model_artifact_hash": manifest["model.bin"]["sha256"],
            "manifest": manifest,
        }
        temp = self.registry_file.with_suffix(".json.tmp")
        temp.write_text(
            json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        temp.replace(self.registry_file)

    def read(self) -> dict[str, Any]:
        if self.registry_file.exists():
            return json.loads(self.registry_file.read_text(encoding="utf-8"))
        return {"schema": 1, "updated_at": _now(), "models": {}}

    def verify(self, key: str, *, full_hash: bool = True) -> dict[str, dict[str, Any]]:
        if key not in MODELS:
            raise ModelError("Model tidak dikenal.")
        folder = self.models_dir / key
        missing = missing_model_files(folder)
        if missing:
            raise ModelError("Model tidak ditemukan atau rusak.")
        manifest: dict[str, dict[str, Any]] = {}
        for path in sorted(folder.rglob("*")):
            if path.is_file() and ".cache" not in path.parts and path.name != ".dnt-manifest.json":
                manifest[path.relative_to(folder).as_posix()] = {
                    "size": path.stat().st_size,
                    "sha256": _sha256(path) if full_hash else "not-checked",
                }
        vocabulary_name = next(name for name in sorted(VOCABULARY_FILES) if name in manifest)
        required_names = [*REQUIRED_FILES, vocabulary_name]
        if any(int(manifest[name]["size"]) <= 0 for name in required_names):
            raise ModelError("Model tidak ditemukan atau rusak.")
        return manifest

    def install_from_hub(self, key: str, downloader: Downloader | None = None) -> Path:
        """Download weights to `.partial`, verify, then atomically promote them."""
        model = MODELS.get(key)
        if model is None:
            raise ModelError("Model tidak dikenal.")
        if shutil.disk_usage(self.models_dir.parent).free < model.expected_size_bytes * 1.5:
            raise ModelError("Ruang disk tidak cukup untuk mengunduh model.")
        final = self.models_dir / key
        if final.exists():
            self.verify(key)
            return final
        partial = self._partial_dir(key)
        partial.mkdir(parents=True)
        try:
            if downloader is None:
                from huggingface_hub import snapshot_download

                snapshot_download(repo_id=model.hf_repo, local_dir=partial)
            else:
                downloader(model.hf_repo, partial)
            manifest = self._verify_folder(partial)
            (partial / ".dnt-manifest.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )
            partial.replace(final)
            self._write_registry(model, manifest, "download")
            return final
        except Exception as exc:
            shutil.rmtree(partial, ignore_errors=True)
            raise ModelError("Model tidak dapat diunduh atau diverifikasi.") from exc

    def import_zip(self, key: str, archive: Path) -> Path:
        model = MODELS.get(key)
        if model is None:
            raise ModelError("Model tidak dikenal.")
        final = self.models_dir / key
        if final.exists():
            self.verify(key)
            return final
        partial = self._partial_dir(key)
        partial.mkdir(parents=True)
        try:
            with zipfile.ZipFile(archive) as package:
                for member in package.infolist():
                    if Path(member.filename).is_absolute() or ".." in Path(member.filename).parts:
                        raise ModelError("Paket model tidak aman.")
                    package.extract(member, partial)
            manifest = self._verify_folder(partial)
            (partial / ".dnt-manifest.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )
            partial.replace(final)
            self._write_registry(model, manifest, "offline_import")
            return final
        except Exception as exc:
            shutil.rmtree(partial, ignore_errors=True)
            if isinstance(exc, ModelError):
                raise
            raise ModelError("Paket model tidak dapat diverifikasi.") from exc

    def _verify_folder(self, folder: Path) -> dict[str, dict[str, Any]]:
        missing = missing_model_files(folder)
        if missing:
            raise ModelError("Model tidak ditemukan atau rusak.")
        return {
            path.relative_to(folder).as_posix(): {
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in sorted(folder.rglob("*"))
            if path.is_file() and ".cache" not in path.parts
        }
