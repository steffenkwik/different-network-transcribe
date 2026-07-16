"""Different Network visual tokens and the shared Qt Widgets stylesheet.

Keep raw colours here rather than scattering them across pages.  The palette is
dark-first by product decision: black surfaces carry the interface, warm yellow
marks the primary path, and orange is reserved for active/attention states.
"""

from __future__ import annotations

from PySide6.QtGui import QColor


class Colors:
    """Semantic colour names for the Different Network desktop interface."""

    CANVAS = "#0D0F12"
    SIDEBAR = "#111419"
    SURFACE = "#171B20"
    SURFACE_RAISED = "#20262D"
    SURFACE_HOVER = "#29313A"
    BORDER = "#37414C"
    BORDER_STRONG = "#566271"
    TEXT = "#F7F8FA"
    TEXT_MUTED = "#B8C0CA"
    TEXT_SUBTLE = "#8C96A3"
    YELLOW = "#F8C63D"
    YELLOW_HOVER = "#FFDA6A"
    YELLOW_PRESSED = "#DCA71F"
    ORANGE = "#F28C28"
    ORANGE_HOVER = "#FFA24B"
    SUCCESS = "#53C78A"
    DANGER = "#F27272"
    INFO = "#6EAEFF"


def qcolor(value: str) -> QColor:
    """Create a QColor from a named design token for custom-painted widgets."""
    return QColor(value)


APP_STYLESHEET = f"""
* {{
    /* Qt Widgets accepts one family here; a CSS-style comma list can select an
       invalid fallback on headless smoke-test platforms. */
    font-family: "Segoe UI";
    font-size: 14px;
    color: {Colors.TEXT};
}}
QMainWindow, QDialog, QWizard {{ background: {Colors.CANVAS}; }}
QWidget#contentArea {{ background: {Colors.CANVAS}; }}
QWidget#sidebar {{ background: {Colors.SIDEBAR}; border-right: 1px solid {Colors.BORDER}; }}
QWidget#pageHeader {{ background: transparent; }}
QLabel#pageTitle {{ font-size: 27px; font-weight: 700; color: {Colors.TEXT}; }}
QLabel#sectionTitle {{ font-size: 18px; font-weight: 700; color: {Colors.TEXT}; }}
QLabel#eyebrow {{ color: {Colors.YELLOW}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QLabel#muted, QLabel#helperText {{ color: {Colors.TEXT_MUTED}; }}
QLabel#subtle {{ color: {Colors.TEXT_SUBTLE}; font-size: 12px; }}
QLabel#brandName {{ color: {Colors.TEXT}; font-size: 16px; font-weight: 700; }}
QLabel#brandProduct {{ color: {Colors.YELLOW}; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
QLabel#statusPill {{ background: {Colors.SURFACE_RAISED}; border: 1px solid {Colors.BORDER};
    border-radius: 12px; color: {Colors.TEXT_MUTED}; padding: 5px 9px; font-size: 12px; }}
QFrame#card, QFrame#metricCard, QFrame#heroCard, QFrame#workflowCard {{
    background: {Colors.SURFACE}; border: 1px solid {Colors.BORDER}; border-radius: 14px;
}}
QFrame#heroCard {{ background: {Colors.SURFACE_RAISED}; border-color: #5B4A18; }}
QFrame#workflowCard {{ background: #1B2026; }}
QLabel#metricValue {{ font-size: 26px; font-weight: 700; color: {Colors.TEXT}; }}
QLabel#metricLabel {{ color: {Colors.TEXT_MUTED}; font-size: 12px; }}
QLabel#accentMetric {{ color: {Colors.YELLOW}; font-size: 26px; font-weight: 700; }}
QPushButton {{
    min-height: 40px; padding: 0 14px; border-radius: 8px; border: 1px solid {Colors.BORDER};
    background: {Colors.SURFACE_RAISED}; color: {Colors.TEXT}; font-weight: 600;
}}
QPushButton:hover {{ background: {Colors.SURFACE_HOVER}; border-color: {Colors.BORDER_STRONG}; }}
QPushButton:pressed {{ background: #11161A; }}
QPushButton:disabled {{ background: #15191D; border-color: #283039; color: #737D88; }}
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QTableWidget:focus, QPlainTextEdit:focus, QCheckBox:focus {{
    border: 2px solid {Colors.YELLOW};
}}
QPushButton#primaryButton {{ background: {Colors.YELLOW}; color: #121416; border-color: {Colors.YELLOW}; }}
QPushButton#primaryButton:hover {{ background: {Colors.YELLOW_HOVER}; border-color: {Colors.YELLOW_HOVER}; }}
QPushButton#primaryButton:pressed {{ background: {Colors.YELLOW_PRESSED}; border-color: {Colors.YELLOW_PRESSED}; }}
QPushButton#warningButton {{ background: {Colors.ORANGE}; color: #17100A; border-color: {Colors.ORANGE}; }}
QPushButton#warningButton:hover {{ background: {Colors.ORANGE_HOVER}; border-color: {Colors.ORANGE_HOVER}; }}
QPushButton#navButton {{ text-align: left; min-height: 42px; border: 0; padding-left: 14px;
    background: transparent; color: {Colors.TEXT_MUTED}; font-weight: 600; }}
QPushButton#navButton:hover {{ color: {Colors.TEXT}; background: {Colors.SURFACE_RAISED}; }}
QPushButton#navButton:checked {{ color: {Colors.TEXT}; background: #3A341F; border-left: 3px solid {Colors.YELLOW}; }}
QLineEdit, QPlainTextEdit, QComboBox {{ background: #12161A; border: 1px solid {Colors.BORDER};
    border-radius: 8px; padding: 8px 10px; selection-background-color: #695818; }}
QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled {{ color: #737D88; }}
QComboBox::drop-down {{ border: 0; width: 26px; }}
QComboBox QAbstractItemView {{ background: {Colors.SURFACE}; border: 1px solid {Colors.BORDER}; selection-background-color: #4E441E; }}
QCheckBox {{ spacing: 8px; color: {Colors.TEXT}; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid {Colors.BORDER_STRONG}; border-radius: 4px; background: #101317; }}
QCheckBox::indicator:checked {{ background: {Colors.YELLOW}; border-color: {Colors.YELLOW}; }}
QRadioButton {{ spacing: 8px; padding: 6px; color: {Colors.TEXT}; }}
QRadioButton::indicator {{ width: 17px; height: 17px; border: 2px solid {Colors.BORDER_STRONG}; border-radius: 9px; }}
QRadioButton::indicator:checked {{ border: 5px solid {Colors.YELLOW}; }}
QTableWidget {{ background: {Colors.SURFACE}; alternate-background-color: #1B2026; border: 1px solid {Colors.BORDER};
    border-radius: 10px; gridline-color: #2B333C; selection-background-color: #4B431F; selection-color: {Colors.TEXT}; }}
QHeaderView::section {{ background: #151A1F; color: {Colors.TEXT_MUTED}; border: 0; border-bottom: 1px solid {Colors.BORDER};
    padding: 9px; font-weight: 700; }}
QProgressBar {{ min-height: 10px; border: 0; border-radius: 5px; background: #101317; text-align: center; color: {Colors.TEXT}; }}
QProgressBar::chunk {{ background: {Colors.YELLOW}; border-radius: 5px; }}
QScrollBar:vertical {{ width: 12px; background: transparent; margin: 4px; }}
QScrollBar::handle:vertical {{ min-height: 28px; border-radius: 5px; background: #4A5663; }}
QScrollBar::handle:vertical:hover {{ background: #637181; }}
QMessageBox QLabel {{ color: {Colors.TEXT}; }}
QWizardPage {{ background: {Colors.CANVAS}; }}
"""
