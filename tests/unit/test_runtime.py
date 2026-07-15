from __future__ import annotations

from app.runtime import bundled_path


def test_development_migrations_resource_exists() -> None:
    assert (bundled_path("migrations") / "0001_initial.sql").is_file()
