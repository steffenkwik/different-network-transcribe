"""Official Different Network Academy assets bundled with the desktop app."""

from __future__ import annotations

from PySide6.QtGui import QFontDatabase, QIcon

from app.runtime import bundled_path


def brand_asset(relative: str) -> str:
    """Return an absolute path to a read-only brand asset in dev or a frozen build."""
    return str(bundled_path(f"assets/{relative}"))


def brand_icon() -> QIcon:
    """Use the approved DN Academy icon for the application and window chrome."""
    return QIcon(brand_asset("brand/dn-favicon.ico"))


def install_brand_fonts() -> None:
    """Load Academy typography without requiring the user to install any fonts.

    Archivo is the product/body family, JetBrains Mono is reserved for compact
    terminal-like labels, and Chakra Petch is used for buttons.  Fonts are
    bundled under their SIL Open Font License files in ``licenses/fonts``.
    """
    for filename in (
        "fonts/Archivo-Variable.ttf",
        "fonts/JetBrainsMono-Variable.ttf",
        "fonts/ChakraPetch-SemiBold.ttf",
    ):
        QFontDatabase.addApplicationFont(brand_asset(filename))
