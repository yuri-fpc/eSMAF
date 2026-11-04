"""Small building blocks shared by the pages."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterable

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as _FigureCanvas
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from . import theme


def title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("pageTitle")
    return label


def lead(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("pageLead")
    label.setWordWrap(True)
    return label


def section(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


def hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


def hairline() -> QFrame:
    line = QFrame()
    line.setObjectName("hairline")
    line.setFixedHeight(1)
    return line


def panel(margin: int = 16, spacing: int = 10) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(spacing)
    return frame, layout


class Note(QFrame):
    """An inline message that says what is wrong, why, and what to do."""

    def __init__(self, severity: str, headline: str, why: str = "", fix: str = "",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName({
            "error": "noteError", "warning": "noteWarning",
            "info": "noteInfo", "ok": "noteOk",
        }.get(severity, "noteInfo"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 10, 13, 10)
        layout.setSpacing(3)

        head = QLabel(headline)
        head.setWordWrap(True)
        head.setStyleSheet(f"font-size:12px;font-weight:600;color:{theme.INK};")
        layout.addWidget(head)
        for text, style in ((why, f"font-size:11.5px;color:{theme.INK_SOFT};"),
                            (fix, f"font-size:11.5px;color:{theme.INK};")):
            if text:
                body = QLabel(text)
                body.setWordWrap(True)
                body.setStyleSheet(style)
                layout.addWidget(body)

        # A word-wrapped label only knows its height once its width is settled.
        # Asking the layout for heightForWidth up front gives the wrong answer,
        # because nested layouts report a width of nearly zero on the first
        # pass; measuring again from the real width on every resize converges
        # immediately and keeps a stack of notes from overlapping.
        policy = self.sizePolicy()
        policy.setVerticalPolicy(QSizePolicy.Policy.Minimum)
        self.setSizePolicy(policy)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        height = self.layout().heightForWidth(max(1, self.width()))
        if height > 0 and height != self.minimumHeight():
            self.setMinimumHeight(height)


class Stat(QWidget):
    """A single number with its label, for the summary strips."""

    def __init__(self, value: str, label: str, color: str | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("stat")
        if color:
            self.value_label.setStyleSheet(
                f"font-size:27px;font-weight:600;color:{color};")
        caption = QLabel(label)
        caption.setObjectName("statLabel")
        caption.setWordWrap(True)
        layout.addWidget(self.value_label)
        layout.addWidget(caption)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class ChecklistRow(QWidget):
    """One line of the project progress checklist."""

    def __init__(self, step: str, done: bool, detail: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(9)

        mark = QLabel("✓" if done else "○")
        mark.setFixedWidth(15)
        mark.setStyleSheet(
            f"font-size:13px;color:{theme.ACCENT if done else theme.INK_FAINT};"
            f"font-weight:{'700' if done else '400'};")
        name = QLabel(step)
        name.setStyleSheet(
            f"font-size:12px;color:{theme.INK if done else theme.INK_SOFT};")
        note = QLabel(detail)
        note.setStyleSheet(f"font-size:11px;color:{theme.INK_FAINT};")
        note.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(mark)
        layout.addWidget(name)
        layout.addStretch(1)
        layout.addWidget(note)


class HelpLink(QPushButton):
    """A question the interface can answer without leaving the flow."""

    def __init__(self, text: str, on_click: Callable[[], None],
                 parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("quiet")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.clicked.connect(lambda: on_click())


#: Column names are internal identifiers; the tables show them in words.
#: The identifier itself is kept for the indicators, because that is what the
#: spreadsheet, the export and the literature all call them, but hovering any
#: heading says what it means and in which unit it was supplied.
CONTEXT_HEADINGS = {
    "land_use": "Land use", "management": "Management", "crop": "Crop",
    "depth": "Depth", "sample": "Sample", "site": "Site", "id": "ID",
}
STATISTIC_SUFFIXES = {"_mean": "mean", "_std": "SD", "_count": "n",
                      "_min": "min", "_max": "max"}
#: WFPS is the one measurement that yields two scores.
WFPS_SHORT = {"WFPS_BiolAct": "WFPS-b", "WFPS_EnvProtect": "WFPS-e"}
WFPS_MEANING = {"WFPS_BiolAct": "biological activity",
                "WFPS_EnvProtect": "environmental protection"}


def _split_statistic(name: str) -> tuple[str, str]:
    for suffix, label in STATISTIC_SUFFIXES.items():
        if name.endswith(suffix):
            return name[: -len(suffix)], label
    return name, ""


def column_heading(name: str) -> str:
    from esmaf_core.indicators import BY_KEY, COMPONENT_LABELS

    base, statistic = _split_statistic(name)
    if base in CONTEXT_HEADINGS:
        head = CONTEXT_HEADINGS[base]
    elif base in BY_KEY:
        head = base
    elif base.endswith("_score"):
        head = f"{WFPS_SHORT.get(base[:-6], base[:-6])} score"
    elif base.endswith("_component"):
        head = COMPONENT_LABELS.get(base[:-10], base[:-10].title())
    elif base == "soil_health_index":
        head = "Soil Health Index"
    elif base == "quality_index":
        head = "Quality index"
    else:
        head = base.replace("_", " ")
    return f"{head} ({statistic})" if statistic else head


def column_tooltip(name: str) -> str:
    from esmaf_core.indicators import BY_KEY, COMPONENT_LABELS

    base, statistic = _split_statistic(name)
    key = base[:-6] if base.endswith("_score") else base
    indicator = BY_KEY.get(key.split("_")[0] if key.startswith("WFPS") else key)
    if indicator is not None:
        what = ("score, 0 to 1" if base.endswith("_score")
                else f"measured value, in {indicator.unit}")
        if key in WFPS_MEANING:
            what = f"{WFPS_MEANING[key]} {what}"
        text = f"{indicator.label} — {what}"
    elif base.endswith("_component"):
        text = (f"{COMPONENT_LABELS.get(base[:-10], base[:-10])} component — "
                "the weighted mean of its indicator scores, 0 to 1")
    elif base == "soil_health_index":
        text = ("Soil Health Index — the weighted mean of all three component "
                "scores, 0 to 1")
    elif base == "quality_index":
        text = ("A partial index: the components that could be computed, "
                "renormalised over themselves, 0 to 1")
    else:
        text = CONTEXT_HEADINGS.get(base, base.replace("_", " "))
    if statistic:
        text += {"mean": ". Mean over the samples in the group",
                 "SD": ". Standard deviation within the group — spread, not significance",
                 "n": ". Number of samples in the group",
                 "min": ". Lowest value in the group",
                 "max": ". Highest value in the group"}[statistic]
    return f"{text}\ncolumn name in the export: {name}"


class DataFrameModel(QAbstractTableModel):
    """A read-only view over a DataFrame that stays fast on large tables.

    Nothing is copied and nothing is pre-rendered, so a hundred thousand rows
    cost the same as a hundred until they are scrolled into view.
    """

    def __init__(self, frame: pd.DataFrame | None = None,
                 highlight: dict[tuple[int, str], str] | None = None):
        super().__init__()
        self._frame = frame if frame is not None else pd.DataFrame()
        self._highlight = highlight or {}
        self._mono = QFont(theme.mono_font())
        self._mono.setPointSizeF(9.0)

    def set_frame(self, frame: pd.DataFrame,
                  highlight: dict[tuple[int, str], str] | None = None) -> None:
        self.beginResetModel()
        self._frame = frame
        self._highlight = highlight or {}
        self.endResetModel()

    @property
    def frame(self) -> pd.DataFrame:
        return self._frame

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._frame)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._frame.columns)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        value = self._frame.iat[index.row(), index.column()]
        column = str(self._frame.columns[index.column()])

        if role == Qt.ItemDataRole.DisplayRole:
            if pd.isna(value):
                return "—"
            if isinstance(value, float):
                return f"{value:,.3f}".rstrip("0").rstrip(".") if abs(value) < 1e6 \
                    else f"{value:.4g}"
            return str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if pd.api.types.is_number(value):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.FontRole and pd.api.types.is_number(value):
            return self._mono
        if role == Qt.ItemDataRole.BackgroundRole:
            severity = self._highlight.get((index.row(), column))
            if severity == "error":
                return QColor(theme.ERROR_SOFT)
            if severity == "warning":
                return QColor(theme.WARNING_SOFT)
        if role == Qt.ItemDataRole.ForegroundRole and pd.isna(value):
            return QColor(theme.INK_FAINT)
        return None

    def headerData(self, index: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            name = str(self._frame.columns[index])
            if role == Qt.ItemDataRole.DisplayRole:
                return column_heading(name)
            if role == Qt.ItemDataRole.ToolTipRole:
                return column_tooltip(name)
            return None
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return str(self._frame.index[index] + 1) if isinstance(self._frame.index[index], int) \
            else str(self._frame.index[index])


class ClickableTable(QWidget):
    """A table that reports which cell was activated, for the drill-down."""

    cell_activated = Signal(int, str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        from PySide6.QtWidgets import QTableView

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.model = DataFrameModel()
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setAlternatingRowColors(True)
        self.view.setSortingEnabled(False)
        self.view.verticalHeader().setDefaultSectionSize(24)
        self.view.verticalHeader().setVisible(False)
        self.view.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
        self.view.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.view.doubleClicked.connect(self._activated)
        layout.addWidget(self.view)

    def _activated(self, index: QModelIndex) -> None:
        if index.isValid():
            column = str(self.model.frame.columns[index.column()])
            self.cell_activated.emit(index.row(), column)

    def set_frame(self, frame: pd.DataFrame,
                  highlight: dict[tuple[int, str], str] | None = None) -> None:
        self.model.set_frame(frame, highlight)
        self.view.resizeColumnsToContents()
        header = self.view.horizontalHeader()
        for column in range(self.model.columnCount()):
            header.resizeSection(column, min(220, max(78, header.sectionSize(column) + 14)))


def clear(layout, keep: int = 0) -> None:
    """Empty a layout, detaching widgets immediately.

    ``deleteLater`` alone leaves the widget parented and painted until the
    event loop next runs, so a page rebuilt twice in one turn draws the old
    widgets on top of the new ones. Detaching first makes the removal
    immediate; the deferred delete then just frees the memory.
    """
    while layout.count() > keep:
        item = layout.takeAt(keep)
        if item is None:
            break
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            clear(item.layout())


def rows(layout: QVBoxLayout, widgets: Iterable[QWidget]) -> None:
    for widget in widgets:
        layout.addWidget(widget)


@contextmanager
def busy(state=None, message: str = ""):
    """Say that something is happening before the window stops responding.

    Scoring twenty thousand samples takes a couple of seconds and writing the
    workbook for them takes ten; without this the window simply freezes, which
    reads as a crash rather than as work in progress.
    """
    QApplication.setOverrideCursor(QCursor(Qt.CursorShape.BusyCursor))
    if state is not None and message:
        state.message.emit("info", message)
    QApplication.processEvents()
    try:
        yield
    finally:
        QApplication.restoreOverrideCursor()
        QApplication.processEvents()


class ChartCanvas(_FigureCanvas):
    """A matplotlib canvas that keeps its layout correct while it is resized."""

    def resizeEvent(self, event):  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        rect = getattr(self.figure, "esmaf_layout_rect", None)
        if rect is None:
            return
        try:
            self.figure.tight_layout(rect=rect)
        except Exception:
            pass  # a layout pass is never worth failing a repaint over
