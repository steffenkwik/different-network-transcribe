"""Official DN identity assets must stay bundled and usable by Qt."""

from __future__ import annotations

import pytest

from app.ui.assets import brand_asset, brand_icon

pytestmark = [pytest.mark.unit]


def test_official_dn_logo_files_are_bundled() -> None:
    assert brand_asset("brand/dn-favicon.ico").endswith("dn-favicon.ico")
    assert brand_asset("brand/dn-favicon.svg").endswith("dn-favicon.svg")


def test_dn_window_icon_is_valid(qtbot) -> None:
    """Qt needs an application object before icon decoding on Windows."""
    assert not brand_icon().isNull()
