"""Official Different Network Academy mark rendered as a scalable SVG."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

from app.ui.assets import brand_asset


class DifferentNetworkMark(QWidget):
    """The approved DN Academy wolf mark, shown without alteration."""

    def __init__(self, parent: QWidget | None = None, size: int = 42) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setToolTip("Logo Different Network")
        self.setAccessibleName("Logo Different Network")
        self._renderer = QSvgRenderer(brand_asset("brand/dn-favicon.svg"), self)

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        if self._renderer.isValid():
            self._renderer.render(painter, QRectF(0, 0, self.width(), self.height()))
        painter.end()
