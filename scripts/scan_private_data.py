"""Private-data scanner (blueprint 17.1, addendum section 21).

The repository is public and git history is permanent: a private file committed once
can never be truly removed. This scanner runs in CI on every pull request and again
before any release asset is built. It fails loudly rather than warning quietly.

It checks the working tree AND, when available, the files git is actually tracking.

Usage:
    python scripts/scan_private_data.py            # scan the repository
    python scripts/scan_private_data.py --path X   # scan a build output directory
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Media, databases and backups must never be tracked.
FORBIDDEN_SUFFIXES = {
    ".opus", ".ogg", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".webm", ".mp4",
    ".sqlite", ".sqlite3", ".db", ".dntbackup",
}

FORBIDDEN_DIR_NAMES = {"Output", "Logs", "Backups", "Models", "Temp", "real-fixtures"}

# Directories that legitimately contain generated or vendored content.
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
             ".ruff_cache", "build", "dist", "node_modules", "htmlcov"}

TEXT_SUFFIXES = {".py", ".md", ".toml", ".txt", ".yml", ".yaml", ".json", ".iss",
                 ".ps1", ".cfg", ".ini"}

# Indonesian mobile numbers and international numbers, e-mail addresses, and the
# operator's real corpus path. None of these belong in a public repository.
PHONE_RE = re.compile(r"(?<![\w.])(?:\+62|62|08)\d[\d\s\-]{7,}\d(?![\w.])")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
REAL_CORPUS_RE = re.compile(r"[A-Za-z]:\\+vn\\+", re.IGNORECASE)
USER_PATH_RE = re.compile(r"[Cc]:\\+Users\\+(?!<)[A-Za-z0-9_.-]+\\+")

# Addresses that are allowed to appear: documentation links and the maintainer's
# own contact string in packaging metadata are not private-data leaks.
EMAIL_ALLOWLIST = {
    "noreply@anthropic.com",
    "orang@contoh.com",       # synthetic example used in a privacy test
    "a.b+x@mail.co.id",       # synthetic example used in a privacy test
}


class Finding:
    def __init__(self, path: Path, reason: str, detail: str = "") -> None:
        self.path = path
        self.reason = reason
        self.detail = detail

    def __str__(self) -> str:
        rel = self.path
        suffix = f" -> {self.detail}" if self.detail else ""
        return f"  {rel}: {self.reason}{suffix}"


def tracked_files() -> list[Path] | None:
    """Files git actually tracks. None when git is unavailable."""
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return [REPO_ROOT / line for line in out.stdout.splitlines() if line.strip()]


def walk_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            found.append(path)
    return found


def scan(paths: list[Path], root: Path, *, check_names_only: bool = False) -> list[Finding]:
    findings: list[Finding] = []

    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path

        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            findings.append(Finding(rel, f"forbidden file type '{path.suffix}'"))
            continue

        if any(part in FORBIDDEN_DIR_NAMES for part in rel.parts[:-1]):
            findings.append(Finding(rel, "lives in a private runtime directory"))
            continue

        if check_names_only or path.suffix.lower() not in TEXT_SUFFIXES:
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        # The scanner's own patterns would match themselves.
        if rel.name == "scan_private_data.py":
            continue

        for match in PHONE_RE.finditer(text):
            findings.append(Finding(rel, "possible real phone number", match.group()[:6] + "..."))

        for match in EMAIL_RE.finditer(text):
            email = match.group()
            if email not in EMAIL_ALLOWLIST and not email.endswith("@example.com"):
                findings.append(Finding(rel, "e-mail address", email))

        if REAL_CORPUS_RE.search(text):
            findings.append(Finding(rel, "reference to the private audio corpus path"))

        for match in USER_PATH_RE.finditer(text):
            findings.append(
                Finding(rel, "user-specific absolute path", match.group().rstrip("\\"))
            )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail if private data is present.")
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Scan this directory (e.g. a build output) instead of the git repository.",
    )
    args = parser.parse_args()

    if args.path is not None:
        root = args.path.resolve()
        targets = walk_files(root)
        # A build output contains binaries; we check names, not the contents of DLLs.
        findings = scan(targets, root, check_names_only=False)
        scope = f"build output {root}"
    else:
        root = REPO_ROOT
        targets = tracked_files()
        if targets is None:
            targets = walk_files(root)
            scope = "working tree (git unavailable)"
        else:
            scope = "git-tracked files"
        findings = scan(targets, root)

    print(f"Private-data scan: {len(targets)} files in {scope}")

    if findings:
        print(f"\nFAILED — {len(findings)} finding(s):\n")
        for finding in findings:
            print(finding)
        print(
            "\nNothing private may enter a public repository or a release asset.\n"
            "Git history is permanent."
        )
        return 1

    print("PASSED — no private data found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
