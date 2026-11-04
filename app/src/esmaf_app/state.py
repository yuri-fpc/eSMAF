"""Application state: the open project and the last analysis run on it."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from esmaf_core.engine import AnalysisResult
from esmaf_core.importer import ImportReport
from esmaf_core.project import Project
from esmaf_core.validation import CheckReport


class AppState(QObject):
    """One open project at a time, with signals so pages stay in step."""

    project_changed = Signal()      # a different project was opened or created
    data_changed = Signal()         # data or column mapping changed
    setup_changed = Signal()        # factor classes or weights changed
    result_changed = Signal()       # an analysis finished
    message = Signal(str, str)      # (severity, text) for the status strip

    def __init__(self) -> None:
        super().__init__()
        self.project = Project()
        self.import_report: ImportReport | None = None
        self.check_report: CheckReport | None = None
        self.result: AnalysisResult | None = None
        self.dirty = False
        self.advanced = False

    # ------------------------------------------------------------ project

    def new_project(self) -> None:
        self.project = Project()
        self.import_report = None
        self.check_report = None
        self.result = None
        self.dirty = False
        self.project_changed.emit()

    def open_project(self, path: str | Path) -> None:
        self.project = Project.load(path)
        self.import_report = None
        self.check_report = None
        self.result = None
        self.dirty = False
        self.project_changed.emit()
        self.message.emit("ok", f"Opened {self.project.name}")

    def save_project(self, path: str | Path | None = None) -> Path:
        target = self.project.save(path)
        self.dirty = False
        self.message.emit("ok", f"Saved to {target.name}")
        self.project_changed.emit()
        return target

    def touch(self, which: str = "data") -> None:
        self.dirty = True
        self.project.touch()
        {"data": self.data_changed, "setup": self.setup_changed,
         "result": self.result_changed}.get(which, self.data_changed).emit()

    @property
    def window_title(self) -> str:
        name = self.project.name or "Untitled project"
        mark = " •" if self.dirty else ""
        return f"{name}{mark} — eSMAF"
