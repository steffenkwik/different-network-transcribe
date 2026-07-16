"""Small vector-like Different Network mark drawn natively by Qt.

It is deliberately a product mark, not a claim that it replaces an official
corporate logo.  Replacing it with an approved asset later changes one widget.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from app.ui.theme import Colors, qcolor


class DifferentNetworkMark(QWidget):
    """A crisp DN monogram made from two linked network paths."""

    def __init__(self, parent: QWidget | None = None, size: int = 42) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setToolTip("Marka Different Network")
        self.setAccessibleName("Marka Different Network")

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(4, 4, self.width() - 8, self.height() - 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(Colors.SURFACE_RAISED))
        painter.drawRoundedRect(rect, 11, 11)

        stroke = max(4.0, rect.width() * 0.16)
        left = QPainterPath()
        left.moveTo(rect.left() + stroke, rect.bottom() - stroke)
        left.lineTo(rect.left() + stroke, rect.top() + stroke)
        left.lineTo(rect.center().x(), rect.center().y())
        left.lineTo(rect.center().x(), rect.bottom() - stroke)
        painter.setPen(QPen(qcolor(Colors.YELLOW), stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(left)

        right = QPainterPath()
        right.moveTo(rect.center().x(), rect.bottom() - stroke)
        right.lineTo(rect.center().x(), rect.top() + stroke)
        right.lineTo(rect.right() - stroke, rect.bottom() - stroke)
        right.lineTo(rect.right() - stroke, rect.top() + stroke)
        painter.setPen(QPen(qcolor(Colors.ORANGE), stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(right)
        painter.end()
