"""Versioned TOML configuration (addendum section 15).

Rules implemented here:
  1. Validate config before use.
  2. Keep a last-known-good copy.
  3. Back up before migration.
  4. Preserve unknown fields when possible  -> tomlkit round-trips the document.
  5. No secrets in v1.
  6. Never store private transcript bodies in config.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.toml_document import TOMLDocument

from app.version import CONFIG_SCHEMA_VERSION

# --------------------------------------------------------------------------
# CPU presets (blueprint 7.2). Derived from the machine at runtime.
# "Do not hardcode the current user's CPU."
# --------------------------------------------------------------------------
CPU_PRESETS: dict[str, float] = {
    "rendah": 0.40,
    "seimbang": 0.70,
    "maksimal": 0.875,
}


def resolve_cpu_threads(preset: str, logical_cpus: int | None = None) -> int:
    """Translate a preset into a concrete thread count for this machine."""
    total = logical_cpus if logical_cpus is not None else (os.cpu_count() or 4)
    fraction = CPU_PRESETS.get(preset, CPU_PRESETS["seimbang"])
    return max(1, min(total, round(total * fraction)))


class ConfigError(ValueError):
    """Configuration failed validation. The caller falls back to last-known-good."""


@dataclass
class TranscriptionConfig:
    """Blueprint 7.2 defaults. These feed the transcript compatibility key."""

    default_model: str = "small"
    review_model: str = "medium"
    language: str = "id"
    task: str = "transcribe"
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 5
    temperature: float = 0.0
    vad_filter: bool = True
    condition_on_previous_text: bool = False
    workers: int = 1
    cpu_preset: str = "seimbang"
    cpu_threads_override: int | None = None
    retry_limit: int = 1

    def resolved_threads(self) -> int:
        if self.cpu_threads_override is not None:
            return max(1, self.cpu_threads_override)
        return resolve_cpu_threads(self.cpu_preset)

    def validate(self) -> None:
        if self.default_model not in ("small", "medium"):
            raise ConfigError(f"default_model tidak dikenal: {self.default_model}")
        if self.review_model not in ("small", "medium"):
            raise ConfigError(f"review_model tidak dikenal: {self.review_model}")
        if self.task != "transcribe":
            # Blueprint 7.1: task 'transcribe', never 'translate'.
            raise ConfigError("task harus 'transcribe'")
        if self.device != "cpu":
            raise ConfigError("v1 hanya mendukung device 'cpu'")
        if self.language not in ("id", "auto"):
            raise ConfigError(f"language tidak didukung: {self.language}")
        if not 1 <= self.beam_size <= 10:
            raise ConfigError("beam_size harus 1-10")
        if not 0.0 <= self.temperature <= 1.0:
            raise ConfigError("temperature harus 0.0-1.0")
        if self.workers != 1:
            raise ConfigError("v1 menggunakan tepat satu worker")
        if self.cpu_preset not in CPU_PRESETS:
            raise ConfigError(f"cpu_preset tidak dikenal: {self.cpu_preset}")
        if not 0 <= self.retry_limit <= 5:
            raise ConfigError("retry_limit harus 0-5")


@dataclass
class MatchingConfig:
    """Addendum section 10."""

    auto_assign_threshold: float = 0.90

    def validate(self) -> None:
        if not 0.5 <= self.auto_assign_threshold <= 1.0:
            raise ConfigError("auto_assign_threshold harus 0.5-1.0")


@dataclass
class UiConfig:
    theme: str = "system"
    page_size: int = 100
    poll_interval_ms: int = 750

    def validate(self) -> None:
        if self.theme not in ("system", "light", "dark"):
            raise ConfigError(f"theme tidak dikenal: {self.theme}")
        if not 10 <= self.page_size <= 500:
            raise ConfigError("page_size harus 10-500")
        if not 500 <= self.poll_interval_ms <= 1000:
            # Addendum section 2: UI refresh every 500-1000 ms.
            raise ConfigError("poll_interval_ms harus 500-1000")


@dataclass
class ExportConfig:
    markdown_daily: bool = True
    markdown_individual: bool = False
    text_daily: bool = True
    text_combined: bool = False
    csv: bool = False
    jsonl: bool = False
    include_technical_metadata: bool = False
    include_generated_at: bool = False  # off => byte-identical re-export (addendum 12)

    def validate(self) -> None:
        return None


@dataclass
class BackupConfig:
    auto_backup_before_migration: bool = True
    keep_backups: int = 10

    def validate(self) -> None:
        if not 1 <= self.keep_backups <= 100:
            raise ConfigError("keep_backups harus 1-100")


@dataclass
class PrivacyConfig:
    """Blueprint section 19. These defaults are the product's promise."""

    telemetry: bool = False
    analytics: bool = False
    crash_upload: bool = False
    log_transcript_bodies: bool = False

    def validate(self) -> None:
        # A config file must never be able to switch the product into a
        # data-exfiltrating mode. There is no code path that uploads anything;
        # these flags exist so that the promise is auditable, and they are pinned.
        if self.telemetry or self.analytics or self.crash_upload:
            raise ConfigError(
                "Aplikasi ini tidak mengirim data ke mana pun. "
                "telemetry/analytics/crash_upload harus false."
            )


@dataclass
class DiagnosticsConfig:
    log_level: str = "INFO"
    keep_log_days: int = 30
    temp_cleanup_hours: int = 24

    def validate(self) -> None:
        if self.log_level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            raise ConfigError(f"log_level tidak dikenal: {self.log_level}")


@dataclass
class PathsConfig:
    audio_roots: list[str] = field(default_factory=list)
    chat_roots: list[str] = field(default_factory=list)

    def validate(self) -> None:
        return None


@dataclass
class AppConfig:
    schema_version: int = CONFIG_SCHEMA_VERSION
    paths: PathsConfig = field(default_factory=PathsConfig)
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    matching: MatchingConfig = field(default_factory=MatchingConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    diagnostics: DiagnosticsConfig = field(default_factory=DiagnosticsConfig)

    # Unknown top-level tables from a newer version are carried through untouched
    # so that downgrading does not silently destroy a future setting (addendum 15.4).
    _unknown: dict[str, Any] = field(default_factory=dict, repr=False)

    def validate(self) -> None:
        if self.schema_version > CONFIG_SCHEMA_VERSION:
            raise ConfigError(
                f"Config dibuat oleh versi yang lebih baru (schema {self.schema_version})."
            )
        for section in (
            self.paths,
            self.transcription,
            self.matching,
            self.ui,
            self.export,
            self.backup,
            self.privacy,
            self.diagnostics,
        ):
            section.validate()


_SECTIONS: dict[str, type] = {
    "paths": PathsConfig,
    "transcription": TranscriptionConfig,
    "matching": MatchingConfig,
    "ui": UiConfig,
    "export": ExportConfig,
    "backup": BackupConfig,
    "privacy": PrivacyConfig,
    "diagnostics": DiagnosticsConfig,
}


def _section_from_table(cls: type, table: Any) -> Any:
    known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
    kwargs = {k: v for k, v in dict(table).items() if k in known}
    return cls(**kwargs)


def from_document(doc: TOMLDocument) -> AppConfig:
    data = dict(doc)
    raw_version = data.get("schema_version", CONFIG_SCHEMA_VERSION)
    cfg = AppConfig(schema_version=int(str(raw_version)))
    for name, cls in _SECTIONS.items():
        if name in data:
            setattr(cfg, name, _section_from_table(cls, data[name]))
    cfg._unknown = {
        k: v for k, v in data.items() if k not in _SECTIONS and k != "schema_version"
    }
    return cfg


def to_document(cfg: AppConfig) -> TOMLDocument:
    doc = tomlkit.document()
    doc.add(tomlkit.comment(" Different Network Transcribe"))
    doc.add(tomlkit.comment(" Berkas ini aman diedit. Salinan terakhir yang valid disimpan"))
    doc.add(tomlkit.comment(" sebagai config.lastgood.toml."))
    doc.add(tomlkit.nl())
    doc["schema_version"] = cfg.schema_version

    for name in _SECTIONS:
        section = getattr(cfg, name)
        table = tomlkit.table()
        for key, value in section.__dict__.items():
            table[key] = value if value is not None else ""
        doc[name] = table

    for key, value in cfg._unknown.items():
        doc[key] = value
    return doc


def load(config_file: Path, lastgood_file: Path | None = None) -> AppConfig:
    """Load, validate, and fall back to last-known-good on failure.

    A corrupt or invalid config never prevents the application from starting.
    """
    if not config_file.exists():
        return AppConfig()

    try:
        doc = tomlkit.parse(config_file.read_text(encoding="utf-8"))
        cfg = from_document(doc)
        cfg.validate()
        return cfg
    except (ConfigError, ValueError, OSError):
        if lastgood_file is not None and lastgood_file.exists():
            try:
                doc = tomlkit.parse(lastgood_file.read_text(encoding="utf-8"))
                cfg = from_document(doc)
                cfg.validate()
                return cfg
            except (ConfigError, ValueError, OSError):
                pass
        return AppConfig()


def save(cfg: AppConfig, config_file: Path, lastgood_file: Path | None = None) -> None:
    """Validate, write atomically, then promote the new file to last-known-good."""
    cfg.validate()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    text = tomlkit.dumps(to_document(cfg))

    temp = config_file.with_suffix(config_file.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(config_file)  # atomic on Windows

    if lastgood_file is not None:
        temp_lg = lastgood_file.with_suffix(lastgood_file.suffix + ".tmp")
        temp_lg.write_text(text, encoding="utf-8")
        temp_lg.replace(lastgood_file)
