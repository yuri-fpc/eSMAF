"""Home: start a project, reopen one, or see where the current one stands."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPlainTextEdit,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from esmaf_core.models import load_model
from esmaf_core.project import SUFFIX, Project

from .. import theme
from ..state import AppState
from ..widgets import (clear, ChecklistRow, Note, hairline, hint, lead, panel,
                       section, title)

RECENT_FILE = Path.home() / ".esmaf" / "recent.json"
MAX_RECENT = 8


def remember(path: Path) -> None:
    RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    entries = read_recent()
    entries = [str(path)] + [e for e in entries if e != str(path)]
    RECENT_FILE.write_text(json.dumps(entries[:MAX_RECENT]), encoding="utf-8")


def read_recent() -> list[str]:
    try:
        return [p for p in json.loads(RECENT_FILE.read_text(encoding="utf-8"))
                if Path(p).exists()]
    except Exception:
        return []


class HomePage(QWidget):
    def __init__(self, state: AppState, go_to, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.state = state
        self.go_to = go_to

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("page")
        scroll.setWidget(body)
        outer.addWidget(scroll)

        layout = QVBoxLayout(body)
        layout.setContentsMargins(34, 30, 34, 30)
        layout.setSpacing(16)

        layout.addWidget(title("eSMAF"))
        layout.addWidget(lead(
            "Soil health scores from your own measurements, computed on this "
            "computer. Nothing is uploaded, and every score can be traced back "
            "to the measurement and the settings that produced it."))
        layout.addSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(10)
        new_button = QPushButton("New project")
        new_button.setObjectName("primary")
        new_button.clicked.connect(self._new)
        open_button = QPushButton("Open project…")
        open_button.clicked.connect(self._open)
        row.addWidget(new_button)
        row.addWidget(open_button)
        row.addStretch(1)
        layout.addLayout(row)

        # --------------------------------------------------------- details
        frame, box = panel()
        box.addWidget(section("This project"))
        self.name_field = QLineEdit()
        self.name_field.setPlaceholderText("Name this study")
        self.name_field.textEdited.connect(self._rename)
        self.description_field = QPlainTextEdit()
        self.description_field.setPlaceholderText(
            "What is being compared, where, and when. This text goes into the report.")
        self.description_field.setFixedHeight(64)
        self.description_field.textChanged.connect(self._redescribe)
        box.addWidget(self.name_field)
        box.addWidget(self.description_field)
        layout.addWidget(frame)

        # -------------------------------------------------------- progress
        self.progress_frame, self.progress_box = panel()
        self.progress_box.addWidget(section("Where this project stands"))
        layout.addWidget(self.progress_frame)

        self.continue_button = QPushButton("Import data")
        self.continue_button.setObjectName("primary")
        self.continue_button.clicked.connect(self._continue)
        continue_row = QHBoxLayout()
        continue_row.addStretch(1)
        continue_row.addWidget(self.continue_button)
        layout.addLayout(continue_row)

        # ---------------------------------------------------------- recent
        self.recent_frame, recent_box = panel()
        recent_box.addWidget(section("Recent projects"))
        self.recent_list = QListWidget()
        self.recent_list.setFixedHeight(132)
        self.recent_list.itemDoubleClicked.connect(self._open_recent)
        recent_box.addWidget(self.recent_list)
        recent_box.addWidget(hint("Double-click to open."))
        layout.addWidget(self.recent_frame)

        # ----------------------------------------------------------- model
        frame, box = panel()
        box.addWidget(section("Calculation model"))
        box.addWidget(hint(
            "Results are stamped with the model that produced them, so an "
            "analysis run today can be compared with one run years ago."))
        self.model_notes = QVBoxLayout()
        self.model_notes.setSpacing(6)
        box.addLayout(self.model_notes)
        layout.addWidget(frame)

        layout.addStretch(1)

        state.project_changed.connect(self.refresh)
        state.data_changed.connect(self.refresh)
        state.setup_changed.connect(self.refresh)
        state.result_changed.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------ actions

    def _new(self) -> None:
        self.state.new_project()
        self.go_to("data")

    def _open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open eSMAF project", "", f"eSMAF project (*{SUFFIX})")
        if path:
            self._load(Path(path))

    def _open_recent(self, item: QListWidgetItem) -> None:
        self._load(Path(item.data(Qt.ItemDataRole.UserRole)))

    def _load(self, path: Path) -> None:
        try:
            self.state.open_project(path)
            remember(path)
            self.go_to("data")
        except Exception as error:  # surfaced, never swallowed
            self.state.message.emit("error", f"Could not open {path.name}: {error}")

    def _rename(self, text: str) -> None:
        self.state.project.name = text
        self.state.dirty = True

    def _redescribe(self) -> None:
        self.state.project.description = self.description_field.toPlainText()
        self.state.dirty = True

    def _continue(self) -> None:
        project = self.state.project
        if not project.has_data:
            self.go_to("data")
        elif not project.ready():
            self.go_to("setup")
        elif self.state.result is None:
            self.go_to("analysis")
        else:
            self.go_to("results")

    # ------------------------------------------------------------ refresh

    def refresh(self) -> None:
        project = self.state.project
        if self.name_field.text() != project.name:
            self.name_field.setText(project.name)
        if self.description_field.toPlainText() != project.description:
            self.description_field.blockSignals(True)
            self.description_field.setPlainText(project.description)
            self.description_field.blockSignals(False)

        clear(self.progress_box, keep=1)
        for step, done, detail in project.progress():
            self.progress_box.addWidget(ChecklistRow(step, done, detail))

        if not project.has_data:
            self.continue_button.setText("Import data")
        elif not project.ready():
            self.continue_button.setText("Set up the analysis")
        elif self.state.result is None:
            self.continue_button.setText("Run the analysis")
        else:
            self.continue_button.setText("See the results")

        self.recent_list.clear()
        for path in read_recent():
            item = QListWidgetItem(f"{Path(path).stem}    {Path(path).parent}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.recent_list.addItem(item)
        self.recent_frame.setVisible(self.recent_list.count() > 0)

        clear(self.model_notes)
        model = load_model(project.model_id)
        self.model_notes.addWidget(Note(
            "ok", f"{model.label}  ({model.id})", model.summary,
            "Every result carries this identifier, so a number produced today "
            "can always be traced back to the parameters behind it.",
        ))
        for departure in model.departures:
            self.model_notes.addWidget(Note(
                "info", f"Adaptation: {departure['item']}",
                f"SMAF: {departure['smaf']}. eSMAF: {departure['esmaf']}.",
                departure.get("reason", ""),
            ))
