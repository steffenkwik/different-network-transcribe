"""Single source of the application identity. Imported by UI, worker, exporters,
backups and the installer script generator, so it must stay dependency-free."""

from __future__ import annotations

APP_NAME = "Different Network Transcribe"
APP_SLUG = "DifferentNetworkTranscribe"
APP_VERSION = "0.2.1"

# Bumped only when the on-disk schema changes. The migration runner is the
# authority; this constant is what backups and diagnostics report.
SCHEMA_VERSION = 5

# Written into export front matter and the .dntbackup manifest.
CONFIG_SCHEMA_VERSION = 1
