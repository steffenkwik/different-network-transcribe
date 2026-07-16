"""Create a user-shareable diagnostic bundle without private source content."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.database.connection import integrity_check, open_connection
from app.version import APP_NAME, APP_VERSION

_PRIVATE_KEYS = frozenset(
    {
        "audio_root",
        "chat_root",
        "data_root",
        "raw_transcript",
        "normalized_transcript",
        "transcript",
        "text",
        "sender",
        "chat",
        "segment_json",
        "msg",
    }
)


def _sanitise(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "<redacted>" if key in _PRIVATE_KEYS else _sanitise(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitise(item) for item in value]
    return value


class DiagnosticsService:
    """Bundle only technical metadata, integrity results and redacted local logs."""

    def __init__(self, database_file: Path, logs_dir: Path, reports_dir: Path, models_dir: Path) -> None:
        self.database_file = database_file
        self.logs_dir = logs_dir
        self.reports_dir = reports_dir
        self.models_dir = models_dir

    def create_bundle(self) -> Path:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
        destination = self.reports_dir / f"DifferentNetworkTranscribe-Diagnostics-{stamp}.zip"
        connection = open_connection(self.database_file, read_only=True)
        try:
            schema_version = int(
                connection.execute("SELECT COALESCE(MAX(version), 0) FROM app_schema_migrations").fetchone()[0]
            )
            report = {
                "application": APP_NAME,
                "app_version": APP_VERSION,
                "database_schema_version": schema_version,
                "database_integrity": integrity_check(connection),
                "created_at": stamp,
                "privacy": "No source audio, chat exports, transcript text, names, or folder paths are included.",
            }
        finally:
            connection.close()
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("report.json", json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            registry = self.models_dir / "registry.json"
            if registry.is_file():
                archive.writestr("models-registry.json", registry.read_text(encoding="utf-8"))
            for log_name in ("ui.log", "worker.log"):
                log_file = self.logs_dir / log_name
                if log_file.is_file():
                    archive.writestr(f"logs/{log_name}", self._redacted_log(log_file))
        return destination

    @staticmethod
    def _redacted_log(path: Path) -> str:
        lines: list[str] = []
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                lines.append("{\"msg\": \"<unparseable local log line omitted>\"}")
            else:
                lines.append(json.dumps(_sanitise(value), ensure_ascii=False, sort_keys=True))
        return "\n".join(lines) + ("\n" if lines else "")
