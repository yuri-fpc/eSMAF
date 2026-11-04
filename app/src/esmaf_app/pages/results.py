"""Results: the scores, two ways of reading them, and where each one came from."""

from __future__ import annotations

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout,
                               QLabel, QPushButton, QScrollArea, QSizePolicy,
                               QSplitter, QTabWidget, QVBoxLayout, QWidget)

from esmaf_core import charts
from esmaf_core import factors as fx
from esmaf_core.engine import score_row_detail
from esmaf_core.indicators import BY_KEY, COMPONENT_LABELS, COMPONENTS
from esmaf_core.models import load_model

from .. import theme
from ..state import AppState
from ..widgets import (ChartCanvas as Canvas, clear, ClickableTable, Note, Stat,
                       hairline, hint, lead, panel, section, title)

ALL = "All"
#: Site is a filter, never an automatic grouping. A soil scientist comparing
#: tillage systems wants the tillage comparison whether or not the samples came
#: from two farms; the site's job is to pick the right curves, which it has
#: already done by the time the results are drawn.
FILTERS = ("site", "land_use", "management", "crop", "depth")


class ResultsPage(QWidget):
    def __init__(self, state: AppState, go_to, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.state = state
        self.go_to = go_to
        self._filters: dict[str, QComboBox] = {}
        self._filter_labels: dict[str, QLabel] = {}
        self._canvases: list[Canvas] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 26, 34, 20)
        layout.setSpacing(12)

        head = QHBoxLayout()
        heading = QVBoxLayout()
        heading.addWidget(title("Results"))
        self.subtitle = lead("")
        heading.addWidget(self.subtitle)
        head.addLayout(heading, 1)
        self.export_button = QPushButton("Export…")
        self.export_button.clicked.connect(lambda: self.go_to("report"))
        head.addWidget(self.export_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(head)

        self.headline = QWidget()
        self.headline_box = QHBoxLayout(self.headline)
        self.headline_box.setContentsMargins(0, 0, 0, 0)
        self.headline_box.setSpacing(34)
        layout.addWidget(self.headline)

        self.notice_box = QVBoxLayout()
        self.notice_box.setSpacing(6)
        layout.addLayout(self.notice_box)

        # ------------------------------------------------------- filter bar
        self.filter_bar = QWidget()
        bar = QHBoxLayout(self.filter_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(9)
        bar.addWidget(QLabel("Showing"))
        for key in FILTERS:
            selector = QComboBox()
            selector.setMinimumWidth(96)
            selector.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            selector.currentIndexChanged.connect(self._apply_filters)
            self._filters[key] = selector
            label = QLabel(key.replace("_", " "))
            self._filter_labels[key] = label
            bar.addWidget(label)
            bar.addWidget(selector)
        reset = QPushButton("Show everything")
        # Five filters plus a button is a tight row on a small window; the
        # button keeps its own width rather than being squeezed into nonsense.
        reset.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        reset.clicked.connect(self._reset_filters)
        bar.addWidget(reset)
        bar.addStretch(1)
        layout.addWidget(self.filter_bar)

        # ------------------------------------------------------------ tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self.charts_scroll = QScrollArea()
        self.charts_scroll.setWidgetResizable(True)
        self.charts_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        charts_body = QWidget()
        charts_body.setObjectName("page")
        self.charts_scroll.setWidget(charts_body)
        self.charts_box = QVBoxLayout(charts_body)
        self.charts_box.setContentsMargins(6, 6, 6, 6)
        self.charts_box.setSpacing(14)
        self.tabs.addTab(self.charts_scroll, "Charts")

        individual = QWidget()
        individual.setObjectName("page")
        individual_box = QVBoxLayout(individual)
        individual_box.setContentsMargins(0, 8, 0, 0)
        individual_box.setSpacing(6)
        individual_box.addWidget(hint(
            "One row per sample. Double-click any score to see how it was produced."))
        self.individual_table = ClickableTable()
        self.individual_table.cell_activated.connect(self._explain)
        individual_box.addWidget(self.individual_table, 1)
        self.tabs.addTab(individual, "Each sample")

        aggregated = QWidget()
        aggregated.setObjectName("page")
        aggregated_box = QVBoxLayout(aggregated)
        aggregated_box.setContentsMargins(0, 8, 0, 0)
        aggregated_box.setSpacing(6)
        aggregated_box.addWidget(hint(
            "Means, spread and sample count for each combination of land use, "
            "management, crop and depth. Descriptive only: no significance test "
            "has been run, so a difference here describes these samples rather "
            "than proving an effect."))
        self.aggregated_table = ClickableTable()
        aggregated_box.addWidget(self.aggregated_table, 1)
        self.tabs.addTab(aggregated, "By group")

        self.provenance_scroll = QScrollArea()
        self.provenance_scroll.setWidgetResizable(True)
        self.provenance_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        provenance_body = QWidget()
        provenance_body.setObjectName("page")
        self.provenance_scroll.setWidget(provenance_body)
        self.provenance_box = QVBoxLayout(provenance_body)
        self.provenance_box.setContentsMargins(6, 10, 6, 6)
        self.provenance_box.setSpacing(9)
        self.tabs.addTab(self.provenance_scroll, "How this was calculated")

        self.empty = Note("info", "Nothing calculated yet",
                          "Results appear here once an analysis has run.",
                          "Go to Analysis check and press Calculate.")
        layout.addWidget(self.empty)

        state.result_changed.connect(self.refresh)
        state.project_changed.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------- filters

    def _reset_filters(self) -> None:
        for selector in self._filters.values():
            selector.blockSignals(True)
            selector.setCurrentIndex(0)
            selector.blockSignals(False)
        self._apply_filters()

    def _rebuild_filters(self) -> None:
        result = self.state.result
        if result is None:
            return
        for key, selector in self._filters.items():
            selector.blockSignals(True)
            current = selector.currentText()
            selector.clear()
            if key in result.scores.columns:
                values = [ALL] + sorted({str(v) for v in result.scores[key]})
                selector.addItems(values)
                if current in values:
                    selector.setCurrentText(current)
                selector.setEnabled(len(values) > 2)
            else:
                selector.addItem(ALL)
                selector.setEnabled(False)
            selector.blockSignals(False)
            # The site filter only earns its place when there is more than one.
            if key == "site":
                several = (key in result.scores.columns
                           and result.scores[key].nunique() > 1)
                selector.setVisible(several)
                self._filter_labels[key].setVisible(several)

    def _filtered(self) -> pd.DataFrame:
        result = self.state.result
        frame = result.scores
        for key, selector in self._filters.items():
            value = selector.currentText()
            if value and value != ALL and key in frame.columns:
                frame = frame[frame[key].astype(str) == value]
        return frame

    def _scope_text(self) -> str:
        parts = [f"{k.replace('_', ' ')}: {s.currentText()}"
                 for k, s in self._filters.items()
                 if s.currentText() and s.currentText() != ALL]
        return "; ".join(parts) if parts else "all samples"

    def _apply_filters(self) -> None:
        if self.state.result is None:
            return
        self._render(self._filtered())

    # -------------------------------------------------------------- render

    def refresh(self) -> None:
        result = self.state.result
        has = result is not None
        self.empty.setVisible(not has)
        self.tabs.setVisible(has)
        self.filter_bar.setVisible(has)
        self.headline.setVisible(has)
        self.export_button.setEnabled(has)
        if not has:
            self.subtitle.setText("")
            return
        self._rebuild_filters()
        self._render(self._filtered())
        self._render_provenance()

    def _render(self, frame: pd.DataFrame) -> None:
        result = self.state.result
        self.subtitle.setText(
            f"{len(frame)} of {result.n_samples} samples  ·  {self._scope_text()}")

        clear(self.headline_box)
        values = frame[result.index_column].dropna() if result.index_column in frame else pd.Series(dtype=float)
        if len(values):
            self.headline_box.addWidget(Stat(
                f"{values.mean():.2f}", result.index_label,
                theme.ACCENT if result.complete_index else theme.WARNING))
            self.headline_box.addWidget(Stat(
                f"{values.min():.2f} – {values.max():.2f}", "Range across samples"))
        for component in COMPONENTS:
            column = f"{component}_component"
            if column in frame.columns and frame[column].notna().any():
                self.headline_box.addWidget(Stat(
                    f"{frame[column].mean():.2f}",
                    f"{COMPONENT_LABELS[component]} component"))
        self.headline_box.addStretch(1)

        clear(self.notice_box)
        if not result.complete_index:
            self.notice_box.addWidget(Note(
                "warning", f"This is a partial index: {result.index_label}",
                "It is renormalised over the components that had data, so it "
                "still runs from 0 to 1, but it covers fewer soil functions.",
                "It should not be compared directly with a complete Soil Health Index."))
        for message in result.warnings[:3]:
            self.notice_box.addWidget(Note("info", message))

        self._render_tables(frame)
        self._render_charts(frame)

    def _render_tables(self, frame: pd.DataFrame) -> None:
        result = self.state.result
        context = [c for c in ("land_use", "management", "crop", "depth", "sample")
                   if c in frame.columns]
        measured = [k for k in result.available_indicators if k in frame.columns]
        columns = context + measured + result.score_columns() + \
            result.component_columns() + [result.index_column]
        columns = [c for c in columns if c in frame.columns]
        self.individual_table.set_frame(frame[columns].reset_index(drop=True))

        from esmaf_core.engine import aggregate
        self.aggregated_table.set_frame(
            aggregate(frame, result.index_column).reset_index(drop=True))

    def _render_charts(self, frame: pd.DataFrame) -> None:
        for canvas in self._canvases:
            canvas.setParent(None)
        self._canvases.clear()
        clear(self.charts_box)

        result = self.state.result
        if frame.empty:
            self.charts_box.addWidget(Note(
                "info", "Nothing matches these filters",
                "", "Widen a filter, or press Show everything."))
            self.charts_box.addStretch(1)
            return

        group = self._group_column(frame)
        scope = self._scope_text()

        figures = []
        score_columns = [c for c in result.score_columns() if c in frame.columns]
        if score_columns:
            figures.append(charts.indicator_scores(
                frame, score_columns, group,
                charts.ChartContext("Indicator scores", scope,
                                    "Colour marks the component.")))
        if group and result.component_columns():
            figures.append(charts.component_scores(
                frame, group,
                charts.ChartContext("Component scores", scope,
                                    "Error bars show spread within the group, "
                                    "not statistical significance.")))
        if group and result.index_column in frame.columns:
            figures.append(charts.index_comparison(
                frame, result.index_column, group, result.index_label,
                result.complete_index,
                charts.ChartContext(result.index_label, scope,
                                    "Open circles are individual samples.")))

        for figure in figures:
            canvas = Canvas(figure)
            canvas.setMinimumHeight(int(figure.get_size_inches()[1] * 96))
            self._canvases.append(canvas)
            self.charts_box.addWidget(canvas)

        row = QHBoxLayout()
        row.addStretch(1)
        save = QPushButton("Save these charts as images…")
        save.clicked.connect(lambda: self._save_charts(figures))
        row.addWidget(save)
        holder = QWidget()
        holder.setLayout(row)
        self.charts_box.addWidget(holder)
        self.charts_box.addStretch(1)

    def _group_column(self, frame: pd.DataFrame) -> str | None:
        """The dimension the charts are panelled by.

        Site is deliberately last: comparing managements is what the user came
        for, and splitting the charts by farm would answer a question they did
        not ask. It is still reachable, by filtering down to one site.
        """
        for key in ("management", "land_use", "crop", "depth"):
            if key in frame.columns and 1 < frame[key].nunique() <= 10:
                return key
        for key in ("land_use", "management", "crop", "depth", "site"):
            if key in frame.columns:
                return key
        return None

    def _save_charts(self, figures) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Save charts into…")
        if not directory:
            return
        from pathlib import Path
        for index, figure in enumerate(figures, start=1):
            target = Path(directory) / f"eSMAF_chart_{index}.png"
            figure.savefig(target, dpi=300, facecolor=charts.SURFACE,
                           bbox_inches="tight")
        self.state.message.emit("ok", f"{len(figures)} chart(s) saved to {directory}")

    # ---------------------------------------------------------- provenance

    def _render_provenance(self) -> None:
        clear(self.provenance_box)
        result = self.state.result
        p = result.provenance

        frame, box = panel(15, 6)
        box.addWidget(section("Versions"))
        for label, value in (
            ("Analysed", p.get("analysis_datetime", "")),
            ("Software", p.get("software_version", "")),
            ("Calculation model", f"{p.get('model_id')} — {p.get('model_label')}"),
            ("Based on", p.get("model_based_on", "")),
            ("Crop database", p.get("crop_db_version", "")),
        ):
            line = QLabel(f"<b>{label}</b>  {value}")
            line.setStyleSheet(f"font-size:11.5px;color:{theme.INK};")
            box.addWidget(line)
        self.provenance_box.addWidget(frame)

        # One panel per site, so a reader can see where two places were
        # described differently — the only reason their samples met different
        # curves.
        for entry in p.get("sites", [{"name": "", "factor_classes":
                                      p.get("factor_classes", {}), "rows": 0}]):
            frame, box = panel(15, 6)
            heading = "Factor classes applied"
            if result.several_sites and entry.get("name"):
                heading = (f"Factor classes applied — {entry['name']} "
                           f"({entry.get('rows', 0)} samples)")
            box.addWidget(section(heading))
            for label, value in fx.describe(entry.get("factor_classes", {})):
                line = QLabel(f"<b>{label}</b>  {value}")
                line.setWordWrap(True)
                line.setStyleSheet(f"font-size:11.5px;color:{theme.INK};")
                box.addWidget(line)
            spellings = entry.get("spellings", [])
            if len(spellings) > 1:
                box.addWidget(hint(
                    "Also written " + ", ".join(f"'{s}'" for s in spellings[1:])
                    + " in the spreadsheet."))
            self.provenance_box.addWidget(frame)

        figure = charts.weight_tree(
            p.get("indicator_weights", {}), p.get("component_weights", {}),
            charts.ChartContext(
                "How weight flows to the index",
                f"{p.get('weighting_scheme_label', '')} — each segment is one "
                f"indicator's share of the index, its weight within its "
                f"component times that component's share"))
        canvas = Canvas(figure)
        canvas.setMinimumHeight(250)
        self._canvases.append(canvas)
        self.provenance_box.addWidget(canvas)

        if result.warnings:
            frame, box = panel(15, 6)
            box.addWidget(section("Warnings raised"))
            for message in result.warnings:
                box.addWidget(Note("warning", message))
            self.provenance_box.addWidget(frame)
        self.provenance_box.addStretch(1)

    # ------------------------------------------------------------ drilldown

    def _explain(self, row_position: int, column: str) -> None:
        if not column.endswith("_score"):
            return
        frame = self._filtered().reset_index(drop=True)
        if row_position >= len(frame):
            return
        record = frame.iloc[row_position]
        key = column[:-6]
        ExplainDialog(self.state, record, key, self).exec()


class ExplainDialog(QDialog):
    """Input value, curve, factor classes, score, contribution -- in one place."""

    def __init__(self, state: AppState, record: pd.Series, score_key: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        result = state.result
        indicator_key = score_key.split("_")[0] if score_key.startswith("WFPS") else score_key
        indicator = BY_KEY[indicator_key]
        self.setWindowTitle(f"How the {indicator.label} score was produced")
        self.resize(720, 720)
        self.setStyleSheet(parent.styleSheet() if parent else "")

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
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        crop_name = str(record.get("crop", ""))
        # The site decides which factor classes shaped this curve, so the
        # drill-down has to look the parameters up by site as well as by crop
        # -- otherwise it would explain a score with another place's soil.
        site_name = result.site_of(record)
        factors = result.factors_for(site_name)
        params = result.parameters.get((site_name, crop_name))
        model = load_model(result.provenance["model_id"])
        traces = score_row_detail(record, None, params, model, factors,
                                  result.available_indicators) if params else {}
        trace = traces.get(score_key)

        layout.addWidget(title(indicator.label))
        layout.addWidget(lead(
            "  ·  ".join(str(record.get(k, "")) for k in
                         ("site", "land_use", "management", "crop", "depth")
                         if k in record)))

        measured = record.get(indicator_key)
        frame, box = panel(15, 7)
        box.addWidget(section("From measurement to score"))
        steps = [
            ("Value you supplied",
             f"{measured:g} {indicator.unit}" if pd.notna(measured) else "—"),
            ("Curve type", indicator.curve.replace("_", "-")),
        ]
        if trace:
            steps += [
                ("Equation", trace.equation),
                ("Branch used", trace.branch or "single branch"),
                ("Score", f"{trace.value:.2f}"),
            ]
            if trace.clipped:
                steps.append(("Note", "The raw value fell outside 0 to 1 and was "
                                      "bounded, as SMAF specifies."))
        for label, value in steps:
            line = QLabel(f"<b>{label}</b>&nbsp;&nbsp;{value}")
            line.setWordWrap(True)
            line.setStyleSheet(f"font-size:12px;color:{theme.INK};")
            box.addWidget(line)
        layout.addWidget(frame)

        # ------------------------------------------------------- the curve
        if trace and pd.notna(measured) and params:
            try:
                low, high = indicator.plausible
                if indicator_key == "WFPS":
                    low, high = 0.0, 1.0
                xs, ys = charts.build_scoring_curve(
                    score_key if score_key.startswith("WFPS") else indicator_key,
                    params, model, factors, low, high)
                figure = charts.scoring_curve(
                    indicator_key, xs, ys, float(measured), trace.value,
                    charts.ChartContext(
                        "The curve this sample was scored against",
                        (f"Built from the factor classes below, for {crop_name} "
                         f"at {site_name}") if result.several_sites else
                        f"Built from the factor classes below, for {crop_name}"))
                canvas = Canvas(figure)
                canvas.setMinimumHeight(300)
                layout.addWidget(canvas)
            except Exception:
                pass  # a drill-down figure is never worth failing the dialog over

        # --------------------------------------------------- what shaped it
        frame, box = panel(15, 6)
        box.addWidget(section(
            f"What shaped this curve — the classes of {site_name}"
            if result.several_sites else "What shaped this curve"))
        affecting = fx.factors_affecting(indicator_key)
        selection = factors.as_dict()
        for factor in affecting:
            code = selection.get(factor.key)
            if code is None:
                continue
            try:
                label = f"{code} — {factor.option(code).label}"
            except KeyError:
                label = str(code)
            line = QLabel(f"<b>{factor.label}</b>&nbsp;&nbsp;{label}")
            line.setWordWrap(True)
            line.setStyleSheet(f"font-size:11.5px;color:{theme.INK};")
            box.addWidget(line)
        if trace and trace.parameters:
            values = ", ".join(
                f"{k} = {v:.6g}" if isinstance(v, (int, float)) else f"{k} = {v}"
                for k, v in trace.parameters.items())
            resolved = QLabel(f"<b>Resolved coefficients</b>&nbsp;&nbsp;{values}")
            resolved.setWordWrap(True)
            resolved.setStyleSheet(f"font-size:11px;color:{theme.INK_SOFT};")
            box.addWidget(resolved)
        layout.addWidget(frame)

        # -------------------------------------------------- contribution up
        frame, box = panel(15, 6)
        box.addWidget(section("What it contributed"))
        weight = result.weights.indicator.get(indicator_key, 0.0)
        if indicator_key == "WFPS":
            weight /= 2
        component_weight = result.weights.component.get(indicator.component, 0.0)
        component_value = record.get(f"{indicator.component}_component")
        index_value = record.get(result.index_column)
        for label, value in (
            (f"Share of the {COMPONENT_LABELS[indicator.component].lower()} component",
             f"{weight * 100:.1f} %"),
            (f"{COMPONENT_LABELS[indicator.component]} component score",
             f"{component_value:.2f}" if pd.notna(component_value) else "—"),
            (f"That component's share of the index", f"{component_weight * 100:.1f} %"),
            (result.index_label, f"{index_value:.2f}" if pd.notna(index_value) else "—"),
        ):
            line = QLabel(f"<b>{label}</b>&nbsp;&nbsp;{value}")
            line.setWordWrap(True)
            line.setStyleSheet(f"font-size:11.5px;color:{theme.INK};")
            box.addWidget(line)
        layout.addWidget(frame)

        note = QLabel(indicator.note)
        note.setWordWrap(True)
        note.setStyleSheet(f"font-size:11.5px;color:{theme.INK_SOFT};")
        layout.addWidget(note)
        if indicator.reference:
            source = QLabel(indicator.reference)
            source.setStyleSheet(f"font-size:10.5px;color:{theme.INK_FAINT};")
            layout.addWidget(source)

        close = QPushButton("Close")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
