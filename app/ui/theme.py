"""Different Network visual tokens and the shared Qt Widgets stylesheet.

Keep raw colours here rather than scattering them across pages.  The palette is
dark-first by product decision: black surfaces carry the interface, the official
DN orange marks the primary path, and chilli red-orange is controlled attention.
"""

from __future__ import annotations

from PySide6.QtGui import QColor


class Colors:
    """Semantic colour names for the Different Network desktop interface."""

    CANVAS = "#060606"
    SIDEBAR = "#0E0E0E"
    SURFACE = "#141414"
    SURFACE_RAISED = "#1C1C1C"
    SURFACE_HOVER = "#252525"
    BORDER = "#303030"
    BORDER_STRONG = "#525252"
    TEXT = "#F5F5F5"
    TEXT_MUTED = "#9A9A9A"
    TEXT_SUBTLE = "#777777"
    ORANGE = "#FF4D00"
    ORANGE_HOVER = "#FF7A3D"
    ORANGE_PRESSED = "#C73C00"
    CHILLI = "#FF2D1A"
    CHILLI_HOVER = "#FF5A4B"
    SUCCESS = "#2ECC71"
    DANGER = "#FF4D4D"
    INFO = "#FF7A3D"


def qcolor(value: str) -> QColor:
    """Create a QColor from a named design token for custom-painted widgets."""
    return QColor(value)


APP_STYLESHEET = f"""
* {{
    /* Qt Widgets accepts one family here; a CSS-style comma list can select an
       invalid fallback on headless smoke-test platforms. */
    font-family: "Archivo";
    font-size: 14px;
    color: {Colors.TEXT};
}}
QMainWindow, QDialog, QWizard {{ background: {Colors.CANVAS}; }}
QWidget#contentArea {{ background: {Colors.CANVAS}; }}
QWidget#sidebar {{ background: {Colors.SIDEBAR}; border-right: 1px solid {Colors.BORDER}; }}
QWidget#pageHeader {{ background: transparent; }}
QLabel#pageTitle {{ font-family: "Archivo"; font-size: 27px; font-weight: 800; color: {Colors.TEXT}; }}
QLabel#sectionTitle {{ font-family: "Archivo"; font-size: 18px; font-weight: 700; color: {Colors.TEXT}; }}
QLabel#eyebrow {{ font-family: "JetBrains Mono"; color: {Colors.ORANGE}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QLabel#muted, QLabel#helperText {{ color: {Colors.TEXT_MUTED}; }}
QLabel#subtle {{ color: {Colors.TEXT_SUBTLE}; font-size: 12px; }}
QLabel#brandName {{ color: {Colors.TEXT}; font-size: 16px; font-weight: 700; }}
QLabel#brandProduct {{ font-family: "JetBrains Mono"; color: {Colors.ORANGE}; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
QLabel#statusPill {{ background: {Colors.SURFACE_RAISED}; border: 1px solid {Colors.BORDER};
    border-radius: 12px; color: {Colors.TEXT_MUTED}; padding: 5px 9px; font-size: 12px; }}
QFrame#card, QFrame#metricCard, QFrame#heroCard, QFrame#workflowCard {{
    background: {Colors.SURFACE}; border: 1px solid {Colors.BORDER}; border-radius: 14px;
}}
QFrame#heroCard {{ background: {Colors.SURFACE_RAISED}; border-color: #7A2A0A; }}
QFrame#workflowCard {{ background: #191919; }}
QLabel#metricValue {{ font-size: 26px; font-weight: 700; color: {Colors.TEXT}; }}
QLabel#metricLabel {{ color: {Colors.TEXT_MUTED}; font-size: 12px; }}
QLabel#accentMetric {{ color: {Colors.ORANGE}; font-size: 26px; font-weight: 700; }}
QPushButton {{
    min-height: 40px; padding: 0 14px; border-radius: 8px; border: 1px solid {Colors.BORDER};
    font-family: "Chakra Petch"; background: {Colors.SURFACE_RAISED}; color: {Colors.TEXT}; font-weight: 600;
}}
QPushButton:hover {{ background: {Colors.SURFACE_HOVER}; border-color: {Colors.BORDER_STRONG}; }}
QPushButton:pressed {{ background: #101010; }}
QPushButton:disabled {{ background: #161616; border-color: #292929; color: #777777; }}
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QTableWidget:focus, QPlainTextEdit:focus, QCheckBox:focus {{
    border: 2px solid {Colors.ORANGE};
}}
QPushButton#primaryButton {{ background: {Colors.ORANGE}; color: {Colors.CANVAS}; border-color: {Colors.ORANGE}; }}
QPushButton#primaryButton:hover {{ background: {Colors.ORANGE_HOVER}; border-color: {Colors.ORANGE_HOVER}; }}
QPushButton#primaryButton:pressed {{ background: {Colors.ORANGE_PRESSED}; border-color: {Colors.ORANGE_PRESSED}; }}
QPushButton#warningButton {{ background: {Colors.CHILLI}; color: {Colors.CANVAS}; border-color: {Colors.CHILLI}; }}
QPushButton#warningButton:hover {{ background: {Colors.CHILLI_HOVER}; border-color: {Colors.CHILLI_HOVER}; }}
QPushButton#dangerButton {{ background: {Colors.DANGER}; color: {Colors.CANVAS}; border-color: {Colors.DANGER}; }}
QPushButton#dangerButton:hover {{ background: #FF7171; border-color: #FF7171; }}
QPushButton#navButton {{ text-align: left; min-height: 42px; border: 0; padding-left: 14px;
    background: transparent; color: {Colors.TEXT_MUTED}; font-weight: 600; }}
QPushButton#navButton:hover {{ color: {Colors.TEXT}; background: {Colors.SURFACE_RAISED}; }}
QPushButton#navButton:checked {{ color: {Colors.TEXT}; background: #2A160C; border-left: 3px solid {Colors.ORANGE}; }}
QLineEdit, QPlainTextEdit, QComboBox {{ background: #101010; border: 1px solid {Colors.BORDER};
    border-radius: 8px; padding: 8px 10px; selection-background-color: #6E2707; }}
QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled {{ color: #777777; }}
QComboBox::drop-down {{ border: 0; width: 26px; }}
QComboBox QAbstractItemView {{ background: {Colors.SURFACE}; border: 1px solid {Colors.BORDER}; selection-background-color: #572006; }}
QCheckBox {{ spacing: 8px; color: {Colors.TEXT}; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid {Colors.BORDER_STRONG}; border-radius: 4px; background: #101010; }}
QCheckBox::indicator:checked {{ background: {Colors.ORANGE}; border-color: {Colors.ORANGE}; }}
QRadioButton {{ spacing: 8px; padding: 6px; color: {Colors.TEXT}; }}
QRadioButton::indicator {{ width: 17px; height: 17px; border: 2px solid {Colors.BORDER_STRONG}; border-radius: 9px; }}
QRadioButton::indicator:checked {{ border: 5px solid {Colors.ORANGE}; }}
QTableWidget {{ background: {Colors.SURFACE}; alternate-background-color: #191919; border: 1px solid {Colors.BORDER};
    border-radius: 10px; gridline-color: #282828; selection-background-color: #542107; selection-color: {Colors.TEXT}; }}
QHeaderView::section {{ font-family: "JetBrains Mono"; background: #101010; color: {Colors.TEXT_MUTED}; border: 0; border-bottom: 1px solid {Colors.BORDER};
    padding: 9px; font-weight: 700; }}
QProgressBar {{ min-height: 10px; border: 0; border-radius: 5px; background: #101010; text-align: center; color: {Colors.TEXT}; }}
QProgressBar::chunk {{ background: {Colors.ORANGE}; border-radius: 5px; }}
QScrollBar:vertical {{ width: 12px; background: transparent; margin: 4px; }}
QScrollBar::handle:vertical {{ min-height: 28px; border-radius: 5px; background: #505050; }}
QScrollBar::handle:vertical:hover {{ background: {Colors.ORANGE}; }}
QMessageBox QLabel {{ color: {Colors.TEXT}; }}
QWizardPage {{ background: {Colors.CANVAS}; }}
"""
