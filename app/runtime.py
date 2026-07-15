"""Resolve read-only bundled resources in development and PyInstaller builds."""

from __future__ import annotations

import sys
from pathlib import Path


def bundled_path(relative: str) -> Path:
    """Return a resource path bundled by PyInstaller or present in the repository."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return root / relative
