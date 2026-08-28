"""Application theme: dark Fusion palette + stylesheet accents.

Pure QSS/QPalette — no image assets, no extra dependencies.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# Central color tokens
BG_WINDOW = "#1b1e24"
BG_PANEL = "#232730"
BG_INPUT = "#2a2f3a"
BORDER = "#3a4150"
TEXT = "#e8eaf0"
TEXT_DIM = "#9aa3b2"
ACCENT = "#4f8cff"
DANGER = "#d9534f"

STYLESHEET = f"""
QMainWindow, QDialog {{
    background-color: {BG_WINDOW};
}}
QWidget {{
    color: {TEXT};
    font-size: 13px;
}}
QLabel {{
    background: transparent;
}}
QGroupBox {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 12px;
    padding: 8px 6px 6px 6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {TEXT_DIM};
    font-weight: bold;
}}
QLineEdit, QDoubleSpinBox, QComboBox {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
}}
QPushButton {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background-color: #333a47;
}}
QPushButton:disabled {{
    color: #6a7180;
    background-color: #242833;
}}
QPushButton#executeButton {{
    background-color: {ACCENT};
    color: white;
    font-weight: bold;
    padding: 6px 22px;
}}
QPushButton#executeButton:hover {{
    background-color: #659aff;
}}
QPushButton#executeButton:disabled {{
    background-color: #33415e;
    color: #8fa2c4;
}}
QPushButton#estopButton {{
    background-color: {DANGER};
    color: white;
    font-weight: bold;
    padding: 6px 16px;
    border: 1px solid #e06663;
}}
QPushButton#estopButton:hover {{
    background-color: #e06663;
}}
QTableWidget {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: {BORDER};
}}
QHeaderView::section {{
    background-color: {BG_INPUT};
    color: {TEXT_DIM};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 4px 6px;
    font-weight: bold;
}}
QPlainTextEdit {{
    background-color: #171a1f;
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: #aeb7c6;
    font-family: Consolas, monospace;
    font-size: 12px;
}}
QProgressBar {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 7px;
    text-align: center;
    color: {TEXT};
    font-weight: bold;
    min-height: 18px;
}}
QProgressBar::chunk {{
    border-radius: 6px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: {BG_WINDOW};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QSplitter::handle {{
    background-color: {BG_WINDOW};
    width: 6px;
}}
QToolTip {{
    background-color: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG_WINDOW))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(BG_PANEL))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_INPUT))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(BG_INPUT))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_INPUT))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_DIM))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
