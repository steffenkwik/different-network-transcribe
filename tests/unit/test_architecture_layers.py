"""Layer rules are enforced, not merely documented.

TECHNICAL_ADDENDUM section 1 lists five rules about what may import what. A rule
that is only written in a document decays the first time someone is in a hurry.
These tests read the actual source with `ast` and fail the build on violation.

They also enforce the product's two loudest promises:
  * no cloud endpoint, no telemetry SDK anywhere in the shipped code;
  * the forbidden label `Tanggal File` never reaches a user (addendum section 14).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Everything below the presentation layer. None of it may know Qt exists.
NON_UI_PACKAGES = [
    "app/models",
    "app/services",
    "app/database",
    "app/transcription",
    "app/parsing",
    "app/matching",
    "app/exports",
    "app/backup",
]

pytestmark = pytest.mark.unit


def _python_files(relative_dir: str) -> list[Path]:
    directory = REPO_ROOT / relative_dir
    if not directory.exists():
        return []
    return sorted(p for p in directory.rglob("*.py") if p.name != "__init__.py")


def _imported_names(path: Path) -> set[str]:
    """Every module name imported by a file, including `from x.y import z` -> 'x.y'."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Identify docstring constants so they are not mistaken for code.

    Without this, a docstring that *describes* a forbidden label would be reported
    as a violation of the rule it documents.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _string_literals(path: Path) -> list[str]:
    """String literals that are actually *used as values* — docstrings excluded."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    skip = _docstring_nodes(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skip
    ]


def _module_level_imports(path: Path) -> set[str]:
    """Imports executed at import time. Imports inside a function body are lazy."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _violations(packages: list[str], forbidden_prefixes: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for package in packages:
        for path in _python_files(package):
            for name in _imported_names(path):
                if name.startswith(forbidden_prefixes):
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    found.append(f"{rel} imports {name}")
    return found


# ---------------------------------------------------------------------------
# Addendum section 1 rule 2: database repositories must not import PySide6.
# We enforce it for the whole non-UI stack, not just repositories: if a service
# can import Qt, business logic starts living in signals and slots.
# ---------------------------------------------------------------------------
def test_no_pyside_below_presentation_layer() -> None:
    found = _violations(NON_UI_PACKAGES, ("PySide6", "shiboken6"))
    assert not found, "Qt must not leak below the presentation layer:\n" + "\n".join(found)


# ---------------------------------------------------------------------------
# Addendum section 1 rule 1: UI code must not contain SQL, transcription logic,
# parser regexes, or filesystem business rules.
# ---------------------------------------------------------------------------
def test_ui_has_no_sql_and_no_engine() -> None:
    found = _violations(["app/ui"], ("sqlite3", "faster_whisper", "ctranslate2", "av"))
    assert not found, "UI must not talk to SQLite or the engine directly:\n" + "\n".join(found)


def test_ui_contains_no_raw_sql() -> None:
    sql_starts = ("select ", "insert ", "update ", "delete ", "create table", "pragma ")
    offenders: list[str] = []
    for path in _python_files("app/ui"):
        for literal in _string_literals(path):
            stripped = literal.strip().lower()
            if stripped.startswith(sql_starts):
                rel = path.relative_to(REPO_ROOT).as_posix()
                offenders.append(f"{rel}: {literal[:60]!r}")
    assert not offenders, "Raw SQL found in the UI layer:\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# Addendum section 1 rule 3: the worker must not manipulate UI widgets.
# It must not even be able to: it never imports Qt.
# ---------------------------------------------------------------------------
def test_worker_never_imports_ui_or_qt() -> None:
    found = _violations(["worker"], ("PySide6", "shiboken6", "app.ui"))
    assert not found, "The worker process must stay Qt-free:\n" + "\n".join(found)


def test_entrypoint_does_not_import_qt_at_module_level() -> None:
    """app/main.py dispatches --worker BEFORE importing Qt.

    If PySide6 were imported at module level, every worker process would pay the
    Qt import cost and load GUI libraries it must never touch.
    """
    main_py = REPO_ROOT / "app" / "main.py"
    top_level = _module_level_imports(main_py)
    qt_at_import_time = {n for n in top_level if n.startswith(("PySide6", "app.ui"))}
    assert not qt_at_import_time, (
        "app/main.py must not import Qt or the UI package at module level; "
        f"the UI import must stay lazy inside main(). Found: {sorted(qt_at_import_time)}"
    )


# ---------------------------------------------------------------------------
# Addendum section 1 rule 4: the domain layer is testable without the UI, which
# means it does no I/O at all.
# ---------------------------------------------------------------------------
def test_domain_layer_does_no_io() -> None:
    found = _violations(
        ["app/models"],
        ("sqlite3", "requests", "httpx", "urllib", "huggingface_hub", "PySide6"),
    )
    assert not found, "The domain layer must be pure:\n" + "\n".join(found)


# ---------------------------------------------------------------------------
# Blueprint section 19 / section 2.2: local only. No cloud API, no telemetry.
# ---------------------------------------------------------------------------
FORBIDDEN_MODULES = (
    "openai",
    "anthropic",
    "boto3",
    "google.cloud",
    "azure",
    "sentry_sdk",
    "posthog",
    "mixpanel",
    "analytics",
    "segment",
)

# The only remote host the product may ever contact, and only to fetch model
# weights that the user explicitly asked for. No audio, no transcript, no name.
ALLOWED_HOSTS = ("huggingface.co", "hf.co")


def test_no_cloud_or_telemetry_sdk_anywhere() -> None:
    found = _violations(["app", "worker"], FORBIDDEN_MODULES)
    assert not found, "Cloud/telemetry SDK found. The product is local-only:\n" + "\n".join(found)


def test_no_unexpected_network_endpoints() -> None:
    offenders: list[str] = []
    for package in ("app", "worker"):
        for path in _python_files(package):
            for literal in _string_literals(path):
                low = literal.lower()
                has_url = "http://" in low or "https://" in low
                if has_url and not any(host in low for host in ALLOWED_HOSTS):
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    offenders.append(f"{rel}: {literal[:80]!r}")
    assert not offenders, (
        "Unexpected network endpoint in shipped code. Only model-weight download "
        "from Hugging Face is permitted:\n" + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# Addendum section 14: a Windows file time is not a WhatsApp time. The generic
# label `Tanggal File` would blur exactly that distinction, so it is forbidden.
# ---------------------------------------------------------------------------
def test_forbidden_tanggal_file_label_is_absent() -> None:
    offenders: list[str] = []
    for package in ("app", "worker"):
        for path in _python_files(package):
            for literal in _string_literals(path):
                if "tanggal file" in literal.lower():
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    offenders.append(f"{rel}: {literal!r}")
    assert not offenders, (
        "The label `Tanggal File` is forbidden (addendum 14). Use "
        "`File dibuat di Windows` / `File diubah di Windows` / `Timestamp WhatsApp`:\n"
        + "\n".join(offenders)
    )


def test_required_timestamp_labels_stay_distinct() -> None:
    from app.resources import strings_id as S

    labels = {S.LABEL_WHATSAPP_TIME, S.LABEL_WINDOWS_CREATED, S.LABEL_WINDOWS_MODIFIED}
    assert len(labels) == 3, "The three timestamp labels must never collapse into each other"
    assert S.UNKNOWN_WHATSAPP_TIME == "Timestamp WhatsApp tidak diketahui"
