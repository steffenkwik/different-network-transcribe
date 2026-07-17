"""Create portable, offline model packs without placing weights in Git."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path

from app.transcription.model_registry import MODELS, ModelError, missing_model_files


def build_model_pack(models_dir: Path, key: str, output_dir: Path) -> Path:
    """Write one verified model ZIP atomically and return its final path.

    The caller explicitly supplies the ignored local model directory.  This
    function never downloads a model and never reads any audio/chat data.
    """
    if key not in MODELS:
        raise ModelError("Model tidak dikenal.")
    source = models_dir / key
    missing = missing_model_files(source)
    if missing:
        raise ModelError("Model tidak ditemukan atau rusak.")
    output_dir.mkdir(parents=True, exist_ok=True)
    final = output_dir / f"DifferentNetworkTranscribe-Model-{key.title()}.zip"
    with tempfile.NamedTemporaryFile(
        suffix=".zip", prefix=f".{key}-", dir=output_dir, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(temporary_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(source.rglob("*")):
                if path.is_file() and ".cache" not in path.parts:
                    archive.write(path, path.relative_to(source).as_posix())
        with temporary_path.open("r+b") as stream:
            os.fsync(stream.fileno())
        temporary_path.replace(final)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return final
