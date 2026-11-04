"""Analysis: the last look before calculating, and the calculation itself."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from esmaf_core import engine
from esmaf_core.crops import UnknownCrop
from esmaf_core.indicators import BY_KEY, COMPONENTS, INDICATORS, indicators_for
from esmaf_core.models import load_model
from esmaf_core.validation import check

from .. import theme
from ..state import AppState
from ..widgets import (Note, busy, clear, hairline, hint, lead, panel,
                       section, title)


class AnalysisPage(QWidget):
    def __init__(self, state: AppState, go_to, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.state = state
        self.go_to = go_to

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 26, 34, 20)
        layout.setSpacing(12)

        layout.addWidget(title("Analysis check"))
        layout.addWidget(lead(
            "What eSMAF is about to compute, and anything that deserves a look "
            "first. A problem stops the calculation; a point to review does not."))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("page")
        scroll.setWidget(body)
        self.box = QVBoxLayout(body)
        self.box.setContentsMargins(0, 4, 8, 4)
        self.box.setSpacing(11)
        layout.addWidget(scroll, 1)

        footer = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("hint")
        footer.addWidget(self.status, 1)
        self.run_button = QPushButton("Calculate")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.run)
        footer.addWidget(self.run_button)
        layout.addLayout(footer)

        state.project_changed.connect(self.refresh)
        state.data_changed.connect(self.refresh)
        state.setup_changed.connect(self.refresh)
        self.refresh()

    # ---------------------------------------------------------------- run

    def run(self) -> None:
        project = self.state.project
        index = project.site_index()
        try:
            with busy(self.state, f"Scoring {len(project.mapped):,} samples…"):
                result = engine.run(
                    project.mapped, project.factors_argument(index.names),
                    project.weights,
                    engine.AnalysisOptions(model_id=project.model_id,
                                           units=dict(project.units),
                                           density_rule=project.density_rule),
                    site_index=index)
        except UnknownCrop as error:
            self.state.message.emit("error", str(error))
            return
        except Exception as error:
            self.state.message.emit("error", f"The calculation stopped: {error}")
            return

        self.state.result = result
        project.record(label=project.name or "analysis",
                       provenance=result.provenance,
                       summary=result.summary_line(),
                       n_samples=result.n_samples)
        self.state.touch("result")
        self.state.message.emit("ok", result.summary_line())
        self.go_to("results")

    # ------------------------------------------------------------ refresh

    def refresh(self) -> None:
        clear(self.box)

        project = self.state.project
        if not project.has_data:
            self.box.addWidget(Note(
                "info", "No data yet",
                "The check runs over the imported table.",
                "Go to Data and drop your spreadsheet in."))
            self.box.addStretch(1)
            self.run_button.setEnabled(False)
            self.status.setText("")
            return

        index = project.site_index()
        report = check(project.mapped, project.factors.as_dict(),
                       project.weights, project.model_id,
                       site_factors=project.selections(index.names)
                       if project.per_site else None,
                       site_index=index, units=project.units,
                       question_open=project.site_question_open())
        self.state.check_report = report

        self.box.addWidget(self._plan_panel())

        if report.errors:
            self.box.addWidget(section(
                f"{len(report.errors)} problem(s) to resolve"))
            for finding in report.errors:
                self.box.addWidget(Note("error", f"{finding.where}: {finding.what}",
                                        finding.why, finding.fix))
        if report.warnings:
            self.box.addWidget(section(
                f"{len(report.warnings)} point(s) to review"))
            for finding in report.warnings:
                self.box.addWidget(Note("warning", f"{finding.where}: {finding.what}",
                                        finding.why, finding.fix))
        if report.infos:
            self.box.addWidget(section("For your information"))
            for finding in report.infos:
                self.box.addWidget(Note("info", f"{finding.where}: {finding.what}",
                                        finding.why, finding.fix))
        if not report.findings:
            self.box.addWidget(Note("ok", "Everything checks out.",
                                    "No problems and nothing unusual was found."))
        self.box.addStretch(1)

        self.run_button.setEnabled(report.can_run)
        self.status.setText(report.summary())
        self.status.setStyleSheet(
            f"font-size:11.5px;color:"
            f"{theme.ERROR if report.errors else theme.ACCENT};")

    def _plan_panel(self) -> QWidget:
        project = self.state.project
        frame, box = panel(15, 8)
        box.addWidget(section("What will be calculated"))

        available = [i for i in INDICATORS if i.key in project.mapped.columns
                     and i.key not in project.weights.excluded]
        covered = [c for c in COMPONENTS
                   if any(i.key in {a.key for a in available}
                          for i in indicators_for(c))]

        from esmaf_core.weights import index_name, is_complete
        label = index_name(tuple(covered))
        complete = is_complete(tuple(covered))

        index = project.site_index()
        if index.from_column and index.several:
            site_line = (
                f"<b>{len(index.sites)}</b> sites: "
                + ", ".join(s.name for s in index.sites)
                + (", each scored with its own factor classes"
                   if project.per_site else
                   ", all scored with the same factor classes"))
        else:
            site_line = ""

        for line in (
            f"<b>{len(project.mapped)}</b> samples, "
            f"<b>{project.mapped['crop'].nunique() if 'crop' in project.mapped else 0}</b> crop(s)",
            site_line,
            f"<b>{len(available)}</b> indicators: "
            + ", ".join(i.label for i in available),
            f"Result: <b>{label}</b>"
            + ("" if complete else
               " — a partial index, because at least one component has no data"),
        ):
            if not line:
                continue
            widget = QLabel(line)
            widget.setWordWrap(True)
            widget.setStyleSheet(f"font-size:12px;color:{theme.INK};")
            box.addWidget(widget)

        box.addWidget(hairline())

        # The calculation model is fixed, not a choice. Offering a menu here
        # invited the one mistake that cannot be caught by any later check: a
        # result computed under parameters the author did not intend. The
        # identifier is still recorded in the provenance of every run, so an
        # older result stays traceable to the model that produced it.
        model = load_model(project.model_id)
        name = QLabel(f"Calculation model: <b>{model.label}</b> "
                      f"<span style='color:{theme.INK_FAINT};'>({model.id})</span>")
        name.setWordWrap(True)
        name.setStyleSheet(f"font-size:12px;color:{theme.INK};")
        box.addWidget(name)
        box.addWidget(hint(model.summary))
        return frame
