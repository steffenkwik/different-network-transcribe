"""Build explicit offline model packs from locally verified model folders.

Usage:
    python scripts/build_model_packs.py --models-dir <app-data>/Models

The command produces ZIPs in ``release/``.  The folders are ignored by Git and
the output is a release asset, never a repository object.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Running ``python scripts/build_model_packs.py`` sets ``scripts/`` as the
# initial import path.  Add the repository root so this explicit release tool
# behaves the same in a clean checkout and in a developer shell.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.transcription.model_packaging import build_model_pack  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Buat paket model offline.")
    parser.add_argument("--models-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("release"))
    parser.add_argument("--model", choices=("small", "medium"), action="append")
    args = parser.parse_args()
    for key in args.model or ["small", "medium"]:
        pack = build_model_pack(args.models_dir, key, args.output_dir)
        print(pack)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
