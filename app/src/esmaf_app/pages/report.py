"""Report and export: take the analysis out of the application."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

from esmaf_core import export_excel, report_pdf

from .. import theme
from ..state import AppState
from ..widgets import (Note, busy, hairline, hint, lead, panel, section,
                       title)

DETAIL_LABELS = {
    "summary": "Summary — the headline result, the settings and the charts",
    "standard": "Standard — adds the group means and every sample",
    "full": "Full record — adds the resolved equation parameters",
}


class ReportPage(QWidget):
    def __init__(self, state: AppState, go_to, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.state = state
        self.go_to = go_to

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 26, 34, 20)
        layout.setSpacing(13)

        layout.addWidget(title("Report and export"))
        layout.addWidget(lead(
            "The report is a record of the analysis, not only its result: "
            "someone who was not involved should be able to read it and know "
            "how each number was produced."))

        # ------------------------------------------------------------- PDF
        frame, box = panel()
        box.addWidget(section("PDF report"))
        row = QHBoxLayout()
        row.addWidget(QLabel("How much detail"))
        self.detail = QComboBox()
        for key, label in DETAIL_LABELS.items():
            self.detail.addItem(label, key)
        self.detail.setCurrentIndex(1)
        row.addWidget(self.detail, 1)
        box.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Prepared by"))
        self.author = QLineEdit()
        self.author.setPlaceholderText("Your name, for the document properties")
        row.addWidget(self.author, 1)
        box.addLayout(row)

        self.include_samples = QCheckBox("List every sample in the report")
        self.include_samples.setChecked(True)
        box.addWidget(self.include_samples)

        button = QPushButton("Write the PDF report…")
        button.setObjectName("primary")
        button.clicked.connect(self._write_pdf)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button)
        box.addLayout(row)
        layout.addWidget(frame)

        # ----------------------------------------------------------- Excel
        frame, box = panel()
        box.addWidget(section("Excel workbook"))
        box.addWidget(hint(
            "One sheet per layer, so nothing overwrites anything: the file as "
            "imported, the values after conversion, the indicator scores, the "
            "component scores, the index, the group means, the resolved "
            "parameters and the warnings."))
        button = QPushButton("Write the workbook…")
        button.clicked.connect(self._write_excel)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button)
        box.addLayout(row)
        layout.addWidget(frame)

        # ------------------------------------------------------------- CSV
        frame, box = panel()
        box.addWidget(section("CSV"))
        box.addWidget(hint("For reading into R, Python or another tool."))
        row = QHBoxLayout()
        row.addStretch(1)
        for label, which in (("Scores by sample…", "scores"),
                             ("Group means…", "aggregated")):
            button = QPushButton(label)
            button.clicked.connect(lambda _, w=which: self._write_csv(w))
            row.addWidget(button)
        box.addLayout(row)
        layout.addWidget(frame)

        # --------------------------------------------------------- project
        frame, box = panel()
        box.addWidget(section("Project file"))
        box.addWidget(hint(
            "Saves the data, the column mapping, the factor classes, the "
            "weights and the analysis history in one file, so reopening it "
            "puts everything back where you left it."))
        button = QPushButton("Save the project…")
        button.clicked.connect(self._save_project)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button)
        box.addLayout(row)
        layout.addWidget(frame)

        self.empty = Note("info", "Nothing to export yet",
                          "Exports are built from a completed analysis.",
                          "Run the analysis first.")
        layout.addWidget(self.empty)
        layout.addStretch(1)

        state.result_changed.connect(self.refresh)
        state.project_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        has = self.state.result is not None
        self.empty.setVisible(not has)
        for index in range(self.layout().count()):
            widget = self.layout().itemAt(index).widget()
            if isinstance(widget, type(self.empty)) or widget is None:
                continue
            if widget.objectName() == "panel":
                widget.setEnabled(has or "Project" in widget.findChild(QLabel).text())

    # ------------------------------------------------------------ writers

    def _default_name(self, suffix: str) -> str:
        name = (self.state.project.name or "eSMAF analysis").strip()
        return f"{name}{suffix}"

    def _write_pdf(self) -> None:
        if self.state.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Write PDF report", self._default_name(" report.pdf"),
            "PDF (*.pdf)")
        if not path:
            return
        try:
            with busy(self.state, "Writing the report…"):
                report_pdf.build(self.state.result, path, report_pdf.ReportOptions(
                    detail=self.detail.currentData(),
                    project_name=self.state.project.name,
                    description=self.state.project.description,
                    author=self.author.text(),
                    include_individual_results=self.include_samples.isChecked(),
                ))
        except Exception as error:
            self.state.message.emit("error", f"The report was not written: {error}")
            return
        self.state.message.emit("ok", f"Report written to {Path(path).name}")

    def _write_excel(self) -> None:
        if self.state.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Write Excel workbook", self._default_name(" results.xlsx"),
            "Excel workbook (*.xlsx)")
        if not path:
            return
        try:
            with busy(self.state, "Writing the workbook…"):
                export_excel.export(self.state.result, path,
                                    project_name=self.state.project.name,
                                    description=self.state.project.description)
        except Exception as error:
            self.state.message.emit("error", f"The workbook was not written: {error}")
            return
        self.state.message.emit("ok", f"Workbook written to {Path(path).name}")

    def _write_csv(self, which: str) -> None:
        result = self.state.result
        if result is None:
            return
        frame = result.scores if which == "scores" else result.aggregated
        path, _ = QFileDialog.getSaveFileName(
            self, "Write CSV", self._default_name(f" {which}.csv"), "CSV (*.csv)")
        if not path:
            return
        with busy(self.state, "Writing the CSV…"):
            frame.to_csv(path, index=False)
        self.state.message.emit("ok", f"CSV written to {Path(path).name}")

    def _save_project(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save project",
            str(self.state.project.path or self._default_name(".esmaf")),
            "eSMAF project (*.esmaf)")
        if not path:
            return
        try:
            with busy(self.state, "Saving the project…"):
                saved = self.state.save_project(path)
        except Exception as error:
            self.state.message.emit("error", f"The project was not saved: {error}")
            return
        from .home import remember
        remember(saved)
