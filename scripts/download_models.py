"""Explicit local model-weight installation; never invoked automatically by the app."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.paths import DataPaths
from app.transcription.model_registry import ModelRegistry


def main() -> int:
    parser = argparse.ArgumentParser(description="Unduh bobot model lokal yang dipilih secara eksplisit.")
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("models", nargs="+", choices=("small", "medium"))
    args = parser.parse_args()
    paths = DataPaths(args.data_dir)
    paths.ensure()
    registry = ModelRegistry(paths.models_dir)
    for key in args.models:
        print(f"Installing {key}...")
        print(registry.install_from_hub(key))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
