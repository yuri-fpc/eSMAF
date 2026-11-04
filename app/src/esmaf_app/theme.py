"""Visual language for the eSMAF desktop application.

The organising idea is the soil profile: work proceeds downwards through a
sequence of horizons, and the navigation rail fills in as each one is
completed.  The chrome is deliberately quiet and instrument-like -- deep
wet-soil greens, paper-neutral working surfaces, iron-oxide reds for anything
that blocks the analysis.  Data keeps its own separate palette (the one in
esmaf_core.charts); chrome colours never appear in a chart and chart colours
never appear in the chrome, so a colour always means one thing.

Type is the platform's own UI face, because this should feel like software
that belongs on the machine rather than a web page in a window.  Numbers in
tables get a tabular face so columns line up -- a legibility decision, not a
stylistic one.
"""

from __future__ import annotations

import sys

# --- surfaces --------------------------------------------------------------
PAPER = "#F7F7F4"          # main working surface
PANEL = "#FFFFFF"          # raised working areas: tables, forms
RAIL = "#22312B"           # navigation rail: deep, wet forest soil
RAIL_ACTIVE = "#3E5C4B"
RAIL_TEXT = "#C9D6CE"
RAIL_TEXT_DIM = "#7E948A"

# --- ink -------------------------------------------------------------------
INK = "#14181A"
INK_SOFT = "#5A6663"
INK_FAINT = "#8B9793"
HAIRLINE = "#DEDEDA"
HAIRLINE_STRONG = "#C4C7C1"

# --- meaning ---------------------------------------------------------------
ACCENT = "#0F6E4F"         # primary actions
ACCENT_HOVER = "#0C5B41"
ACCENT_SOFT = "#E4EFEA"
ERROR = "#B4472C"          # blocks the analysis; oxidised iron
ERROR_SOFT = "#FAEDE9"
WARNING = "#B07A17"        # worth a second look; goethite
WARNING_SOFT = "#FBF3E2"
INFO = "#2A5B8C"
INFO_SOFT = "#EAF0F7"

# --- horizon bands, one per workflow step ---------------------------------
# Lightest at the top, as an A horizon grades into a B.
HORIZONS = ("#6E8C7A", "#5C7D69", "#4C6E5A", "#3E5F4C", "#31513F", "#264434")


def ui_font() -> str:
    if sys.platform == "win32":
        return "Segoe UI"
    if sys.platform == "darwin":
        return "SF Pro Text"
    return "Inter, Cantarell, DejaVu Sans"


def mono_font() -> str:
    if sys.platform == "win32":
        return "Consolas"
    if sys.platform == "darwin":
        return "SF Mono"
    return "DejaVu Sans Mono"


def stylesheet() -> str:
    ui = ui_font()
    mono = mono_font()
    return f"""
* {{ font-family: "{ui}"; }}

QMainWindow, QDialog {{ background: {PAPER}; }}
QWidget#page {{ background: {PAPER}; }}

/* ---------------------------------------------------------------- rail */
QFrame#rail {{ background: {RAIL}; border: none; }}
QLabel#railBrand {{
    color: #FFFFFF; font-size: 17px; font-weight: 600;
    padding: 20px 18px 2px 18px; letter-spacing: 0.2px;
}}
QLabel#railTagline {{
    color: {RAIL_TEXT_DIM}; font-size: 10.5px; padding: 0 18px 18px 18px;
}}
QLabel#railFooter {{
    color: {RAIL_TEXT_DIM}; font-size: 10px; padding: 10px 18px 16px 18px;
}}

QPushButton#railStep {{
    background: transparent; border: none; color: {RAIL_TEXT};
    text-align: left; padding: 11px 16px 11px 14px; font-size: 12.5px;
    border-left: 3px solid transparent;
}}
QPushButton#railStep:hover {{ background: rgba(255,255,255,0.06); }}
QPushButton#railStep:checked {{
    background: rgba(255,255,255,0.10); color: #FFFFFF; font-weight: 600;
}}
QPushButton#railStep:disabled {{ color: {RAIL_TEXT_DIM}; }}

/* -------------------------------------------------------------- headers */
QLabel#pageTitle {{ font-size: 21px; font-weight: 600; color: {INK}; }}
QLabel#pageLead {{ font-size: 12.5px; color: {INK_SOFT}; }}
QLabel#sectionTitle {{ font-size: 13.5px; font-weight: 600; color: {INK};
                       padding-top: 4px; }}
QLabel#hint {{ font-size: 11.5px; color: {INK_SOFT}; }}
QLabel#stat {{ font-size: 27px; font-weight: 600; color: {INK}; }}
QLabel#statLabel {{ font-size: 11px; color: {INK_SOFT}; }}

/* --------------------------------------------------------------- panels */
QFrame#panel {{
    background: {PANEL}; border: 1px solid {HAIRLINE}; border-radius: 6px;
}}
QFrame#dropZone {{
    background: {PANEL}; border: 2px dashed {HAIRLINE_STRONG}; border-radius: 8px;
}}
QFrame#dropZoneActive {{
    background: {ACCENT_SOFT}; border: 2px dashed {ACCENT}; border-radius: 8px;
}}
QFrame#hairline {{ background: {HAIRLINE}; max-height: 1px; border: none; }}

QFrame#noteError {{ background: {ERROR_SOFT}; border: none;
                    border-left: 3px solid {ERROR}; border-radius: 3px; }}
QFrame#noteWarning {{ background: {WARNING_SOFT}; border: none;
                      border-left: 3px solid {WARNING}; border-radius: 3px; }}
QFrame#noteInfo {{ background: {INFO_SOFT}; border: none;
                   border-left: 3px solid {INFO}; border-radius: 3px; }}
QFrame#noteOk {{ background: {ACCENT_SOFT}; border: none;
                 border-left: 3px solid {ACCENT}; border-radius: 3px; }}

/* -------------------------------------------------------------- buttons */
QPushButton {{
    background: {PANEL}; border: 1px solid {HAIRLINE_STRONG}; border-radius: 5px;
    padding: 7px 15px; font-size: 12px; color: {INK};
}}
QPushButton:hover {{ background: #F0F1EE; }}
QPushButton:pressed {{ background: #E6E8E3; }}
QPushButton:disabled {{ color: {INK_FAINT}; background: #F2F2EF;
                        border-color: {HAIRLINE}; }}
QPushButton#primary {{
    background: {ACCENT}; border: 1px solid {ACCENT}; color: #FFFFFF;
    font-weight: 600; padding: 8px 20px;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton#primary:disabled {{ background: #A8BDB2; border-color: #A8BDB2;
                                color: #EDF3F0; }}
QPushButton#quiet {{ background: transparent; border: none; color: {ACCENT};
                     padding: 4px 6px; text-decoration: underline; }}
QPushButton#quiet:hover {{ color: {ACCENT_HOVER}; }}

/* --------------------------------------------------------------- inputs */
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {PANEL}; border: 1px solid {HAIRLINE_STRONG}; border-radius: 5px;
    padding: 6px 9px; font-size: 12px; color: {INK}; selection-background-color: {ACCENT_SOFT};
    selection-color: {INK};
}}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {PANEL}; border: 1px solid {HAIRLINE_STRONG};
    selection-background-color: {ACCENT_SOFT}; selection-color: {INK};
    padding: 4px; outline: none;
}}
QLineEdit[state="error"], QDoubleSpinBox[state="error"] {{ border-color: {ERROR}; }}

QCheckBox, QRadioButton {{ font-size: 12px; color: {INK}; spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}

/* --------------------------------------------------------------- tables */
QTableView, QTreeWidget, QListWidget {{
    background: {PANEL}; border: 1px solid {HAIRLINE}; border-radius: 6px;
    gridline-color: #EFEFEC; font-size: 11.5px; color: {INK};
    selection-background-color: {ACCENT_SOFT}; selection-color: {INK};
    alternate-background-color: #FBFBF9;
}}
QHeaderView::section {{
    background: #F1F2EE; border: none; border-right: 1px solid {HAIRLINE};
    border-bottom: 1px solid {HAIRLINE_STRONG};
    padding: 7px 9px; font-size: 11px; font-weight: 600; color: {INK_SOFT};
}}
QTableView::item {{ padding: 3px 6px; }}
QTableView#numeric {{ font-family: "{mono}"; }}

/* ----------------------------------------------------------------- tabs */
QTabWidget::pane {{ border: 1px solid {HAIRLINE}; border-radius: 6px;
                    background: {PANEL}; top: -1px; }}
QTabBar::tab {{
    background: transparent; border: none; padding: 8px 16px;
    font-size: 12px; color: {INK_SOFT}; margin-right: 2px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {INK}; font-weight: 600;
                         border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover:!selected {{ color: {INK}; }}

/* --------------------------------------------------------------- status */
QFrame#statusStrip {{ background: {PANEL}; border-top: 1px solid {HAIRLINE}; }}
QLabel#statusText {{ font-size: 11px; color: {INK_SOFT}; }}
QLabel#statusValue {{ font-size: 11px; color: {INK}; font-weight: 600; }}

QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #CFD2CB; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #B6BAB2; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #CFD2CB; border-radius: 5px; min-width: 30px; }}

QToolTip {{
    background: {INK}; color: #FFFFFF; border: none; padding: 7px 9px;
    font-size: 11.5px;
}}

QSplitter::handle {{ background: {HAIRLINE}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QProgressBar {{ border: none; background: {HAIRLINE}; border-radius: 3px;
                height: 5px; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
"""
