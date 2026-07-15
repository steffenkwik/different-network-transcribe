"""Entry point for both roles.

One executable, two roles (IMPLEMENTATION_PLAN section 4):
    DifferentNetworkTranscribe.exe                 -> UI
    DifferentNetworkTranscribe.exe --worker ...    -> transcription worker

The --worker flag is inspected BEFORE PySide6 is imported, so the worker process
never loads Qt. That keeps worker memory bounded and makes the "worker must not
manipulate UI widgets" rule structurally true rather than merely a convention.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="DifferentNetworkTranscribe",
        description="Transkripsi lokal catatan suara WhatsApp.",
    )
    parser.add_argument(
        "--worker",
        action="store_true",
        help="Jalankan sebagai proses worker transkripsi (internal).",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Folder data. Wajib untuk --worker.",
    )
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Instance token sesi worker (internal).",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help=(
            "Buka jendela, pastikan tampil, lalu keluar. Dipakai untuk smoke test "
            "installer dan paket portable."
        ),
    )
    parser.add_argument(
        "--engine-import-self-test",
        action="store_true",
        help="Periksa dependensi mesin transkripsi tanpa membaca atau memproses audio.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])

    if args.engine_import_self_test:
        # This intentionally does not load a model or open an audio file. It is a
        # packaging gate for native NumPy/faster-whisper dependencies.
        import faster_whisper
        import numpy

        print(f"ENGINE_IMPORT_SELF_TEST PASS numpy={numpy.__version__} faster_whisper={faster_whisper.__version__}")
        return 0

    if args.worker:
        if args.data_dir is None or args.session is None:
            print("--worker membutuhkan --data-dir dan --session", file=sys.stderr)
            return 2
        # Imported lazily: this module must not pull in PySide6.
        from worker.main import run_worker

        return run_worker(data_dir=args.data_dir, instance_token=args.session)

    from app.ui.launch import run_ui

    return run_ui(data_dir=args.data_dir, self_test=args.self_test)


if __name__ == "__main__":
    raise SystemExit(main())
