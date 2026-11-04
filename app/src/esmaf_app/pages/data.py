"""Data: bring a spreadsheet in, agree on what its columns mean, check it."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout,
                               QLabel, QPushButton, QScrollArea, QSplitter,
                               QTabWidget, QVBoxLayout, QWidget)

from esmaf_core import importer
from esmaf_core import units as un
from esmaf_core.indicators import BY_KEY, CONTEXT_COLUMNS, INDICATORS
from esmaf_core.validation import check

from .. import theme
from ..state import AppState
from ..widgets import (busy, clear, ClickableTable, Note, hairline, hint, lead,
                       panel, section, title)

IGNORE = "— not used —"


class DropZone(QFrame):
    """Drag a file onto the window; the usual way to open something on a desktop."""

    def __init__(self, on_file, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.on_file = on_file
        self.setMinimumHeight(132)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        headline = QLabel("Drop a spreadsheet here")
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        headline.setStyleSheet(f"font-size:14.5px;font-weight:600;color:{theme.INK};")
        detail = QLabel("Excel or CSV. Column names are recognised automatically, "
                        "and you can correct any of them before calculating.")
        detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail.setWordWrap(True)
        detail.setStyleSheet(f"font-size:11.5px;color:{theme.INK_SOFT};")

        browse = QPushButton("Choose a file…")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(browse)
        row.addStretch(1)

        layout.addWidget(headline)
        layout.addWidget(detail)
        layout.addLayout(row)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open data", "",
            "Spreadsheets (*.xlsx *.xlsm *.xls *.csv *.tsv);;All files (*)")
        if path:
            self.on_file(Path(path))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            self.setObjectName("dropZoneActive")
            self.setStyleSheet("")
            self.style().polish(self)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self.setObjectName("dropZone")
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setObjectName("dropZone")
        self.style().polish(self)
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_file():
                self.on_file(path)
                break


class DataPage(QWidget):
    def __init__(self, state: AppState, go_to, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.state = state
        self.go_to = go_to
        self.setAcceptDrops(True)
        self._selectors: dict[str, QComboBox] = {}
        self._units: dict[str, QComboBox] = {}
        self._preset_box: QComboBox | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 26, 34, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.addWidget(title("Data"))
        heading.addWidget(lead(
            "Your measurements, exactly as you recorded them. eSMAF keeps this "
            "table untouched and writes every result into a separate layer."))
        header.addLayout(heading, 1)
        self.template_button = QPushButton("Save a blank template…")
        self.template_button.clicked.connect(self._save_template)
        self.replace_button = QPushButton("Replace data…")
        self.replace_button.clicked.connect(self._browse)
        header.addWidget(self.template_button, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(self.replace_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        self.drop = DropZone(self.load_file)
        layout.addWidget(self.drop)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter, 1)

        # ------------------------------------------------------- left: data
        left = QWidget()
        left.setObjectName("page")
        left_box = QVBoxLayout(left)
        left_box.setContentsMargins(0, 0, 0, 0)
        left_box.setSpacing(8)
        self.summary_label = QLabel()
        self.summary_label.setObjectName("hint")
        # Without word wrap this label reports its full single-line width as a
        # minimum, which propagated up and froze the splitter: the left pane
        # could never shrink, so the handle would not move and the mapping
        # panel was squeezed off the page.
        self.summary_label.setWordWrap(True)
        self.summary_label.setMinimumWidth(1)
        left_box.addWidget(self.summary_label)
        self.tabs = QTabWidget()
        self.raw_table = ClickableTable()
        self.mapped_table = ClickableTable()
        self.tabs.addTab(self.raw_table, "As imported")
        self.tabs.addTab(self.mapped_table, "As eSMAF reads it")
        left_box.addWidget(self.tabs, 1)
        left.setMinimumWidth(360)
        self.splitter.addWidget(left)

        # -------------------------------------------------- right: mapping
        right = QScrollArea()
        right.setWidgetResizable(True)
        right.setFrameShape(QScrollArea.Shape.NoFrame)
        right_body = QWidget()
        right_body.setObjectName("page")
        right.setWidget(right_body)
        self.right_box = QVBoxLayout(right_body)
        self.right_box.setContentsMargins(14, 0, 4, 0)
        self.right_box.setSpacing(10)
        right.setMinimumWidth(360)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes([660, 480])

        footer = QHBoxLayout()
        self.check_summary = QLabel()
        self.check_summary.setObjectName("hint")
        footer.addWidget(self.check_summary, 1)
        self.next_button = QPushButton("Continue to setup")
        self.next_button.setObjectName("primary")
        self.next_button.clicked.connect(lambda: self.go_to("setup"))
        footer.addWidget(self.next_button)
        layout.addLayout(footer)

        state.project_changed.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------ loading

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_file():
                self.load_file(path)
                break

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open data", "",
            "Spreadsheets (*.xlsx *.xlsm *.xls *.csv *.tsv);;All files (*)")
        if path:
            self.load_file(Path(path))

    def _save_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save blank template", "eSMAF_template.xlsx",
            "Excel workbook (*.xlsx);;CSV (*.csv)")
        if path:
            importer.write_template(path)
            self.state.message.emit("ok", f"Template written to {Path(path).name}")

    def load_file(self, path: Path, sheet: str | int | None = None) -> None:
        """Import a spreadsheet. ``sheet`` skips the picker, for scripted runs."""
        try:
            sheets = importer.list_sheets(path)
            if sheet is None and len(sheets) > 1:
                from PySide6.QtWidgets import QInputDialog
                sheet, ok = QInputDialog.getItem(
                    self, "Which sheet?",
                    f"{path.name} has {len(sheets)} sheets. Which one holds the data?",
                    sheets, 0, False)
                if not ok:
                    return
            with busy(self.state, f"Reading {path.name}…"):
                report = importer.load(path, sheet)
        except Exception as error:
            self.state.message.emit(
                "error", f"Could not read {path.name}: {error}")
            return

        project = self.state.project
        project.raw = report.original
        project.mapped = report.frame
        project.source_file = str(path)
        project.source_sheet = report.sheet or ""
        project.column_mapping = {m.source: m.target for m in report.mappings}
        # New columns, new headers: whatever preset was chosen for the previous
        # file says nothing about this one.
        project.units = {}
        project.unit_preset = None
        project.declare_units({m.target: m.unit for m in report.mappings
                               if m.target and m.unit})
        self.state.import_report = report
        self.state.result = None
        self.state.touch("data")
        self.state.message.emit("ok", f"{path.name}: {report.describe()}")
        self.refresh()

    # ------------------------------------------------------------- mapping

    def _rebuild_mapping_panel(self) -> None:
        clear(self.right_box)
        self._selectors.clear()

        report = self.state.import_report
        if report is None:
            self.right_box.addWidget(hint(
                "Once a file is loaded, its columns are listed here with what "
                "eSMAF thinks each one is."))
            self.right_box.addStretch(1)
            return

        self.right_box.addWidget(section("Column meanings"))
        self.right_box.addWidget(hint(
            "Change anything that was read wrongly. Nothing is calculated from "
            "a column marked as not used."))

        targets = [IGNORE]
        targets += [f"{c}  ·  grouping" for c in CONTEXT_COLUMNS]
        targets += [f"{i.key}  ·  {i.label} ({i.unit})" for i in INDICATORS]

        unrecognised = [m for m in report.mappings if not m.target]
        if unrecognised:
            names = ", ".join(f"'{m.source}'" for m in unrecognised[:6])
            more = f" and {len(unrecognised) - 6} more" if len(unrecognised) > 6 else ""
            suggestions = [m for m in unrecognised if m.suggestions]
            fix = ""
            if suggestions:
                first = suggestions[0]
                fix = (f"'{first.source}' looks close to "
                       f"'{first.suggestions[0]}'. Set it below if that is what it is.")
            self.right_box.addWidget(Note(
                "warning", f"{len(unrecognised)} column(s) not recognised: {names}{more}",
                "Unrecognised columns are carried through untouched and are not "
                "used in any calculation.", fix))

        frame, box = panel(12, 6)
        for mapping in report.mappings:
            row = QHBoxLayout()
            row.setSpacing(8)
            name = QLabel(mapping.source)
            name.setFixedWidth(116)
            name.setWordWrap(True)
            name.setStyleSheet(f"font-size:11.5px;color:{theme.INK};")
            selector = QComboBox()
            selector.setMinimumWidth(150)
            selector.addItems(targets)
            selector.setCurrentIndex(self._index_of(mapping.target, targets))
            selector.currentIndexChanged.connect(
                lambda _, source=mapping.source, box=selector: self._remap(source, box))
            self._selectors[mapping.source] = selector
            row.addWidget(name)
            row.addWidget(selector, 1)
            box.addLayout(row)
        self.right_box.addWidget(frame)
        self._build_units()
        self.right_box.addStretch(1)

    # --------------------------------------------------------------- units

    def _build_units(self) -> None:
        """Which unit each measurement arrived in.

        The only property of the data that the data cannot reveal. Organic
        carbon of 3.7 per cent and organic matter of 3.7 g dm-3 are the same
        number and describe soils an order of magnitude apart, so eSMAF reads
        the unit from the header where the header states one and asks where it
        does not, rather than assuming the template was followed.
        """
        project = self.state.project
        self._units.clear()
        self._preset_box = None
        if not project.has_data:
            return
        needed = [i for i in INDICATORS if i.key in project.mapped.columns
                  and un.must_be_declared(i.key)]
        if not needed:
            return

        self.right_box.addWidget(section("Units"))
        missing = project.units_missing()
        if missing:
            self.right_box.addWidget(Note(
                "error", f"{len(missing)} column(s) have not said what unit they are in",
                "A routine Brazilian report gives phosphorus per cubic "
                "decimetre, potassium as charge and organic matter rather than "
                "carbon. None of that shows in the number.",
                "Set each one below, or use a preset."))

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Preset"))
        presets = QComboBox()
        presets.addItem("— choose one —", None)
        for preset in un.PRESETS:
            presets.addItem(preset.label, preset.id)
        # The selector reads its state back from the units themselves, not from
        # what was last clicked, so editing one dropdown by hand drops it back
        # to "choose one" rather than leaving a preset named that no longer
        # describes the data.
        current_preset = un.matching_preset(project.units, [i.key for i in needed],
                                            prefer=project.unit_preset)
        presets.blockSignals(True)
        presets.setCurrentIndex(max(0, presets.findData(current_preset))
                                if current_preset else 0)
        presets.blockSignals(False)
        presets.currentIndexChanged.connect(
            lambda: self._apply_preset(presets.currentData()))
        self._preset_box = presets
        row.addWidget(presets, 1)
        self.right_box.addLayout(row)
        chosen = un.preset(current_preset) if current_preset else None
        if chosen is None:
            self.right_box.addWidget(hint(
                "A preset fills the list below in one step. Every value stays "
                "editable, and what is chosen here is recorded with the result."))
        else:
            self.right_box.addWidget(hint(chosen.description))
            same = un.equivalent_presets(chosen.id, [i.key for i in needed])
            if same:
                self.right_box.addWidget(hint(
                    "For the columns in this dataset this is the same set of "
                    "units as " + ", ".join(
                        f"\u201c{un.preset(other).label}\u201d" for other in same)
                    + ", so nothing below changes. SMAF's curves are defined per "
                      "kilogram, which is why the mass-basis conventions and the "
                      "eSMAF template coincide."))

        frame, box = panel(12, 6)
        for indicator in needed:
            line = QHBoxLayout()
            line.setSpacing(8)
            name = QLabel(indicator.label)
            name.setFixedWidth(116)
            name.setWordWrap(True)
            name.setStyleSheet(f"font-size:11.5px;color:{theme.INK};")
            selector = QComboBox()
            selector.setMinimumWidth(150)
            selector.addItem("— state the unit —", None)
            for unit in un.options(indicator.key):
                selector.addItem(unit.label, unit.id)
            current = project.units.get(indicator.key)
            position = selector.findData(current) if current else 0
            selector.setCurrentIndex(max(0, position))
            selector.currentIndexChanged.connect(
                lambda _, key=indicator.key, s=selector:
                    self._set_unit(key, s.currentData()))
            self._units[indicator.key] = selector
            line.addWidget(name)
            line.addWidget(selector, 1)
            box.addLayout(line)
            unit = un.get(indicator.key, current) if current else None
            if unit is not None and not unit.native:
                box.addWidget(hint(f"    {unit.note}"))
        self.right_box.addWidget(frame)

        if project.uses_volume_basis():
            self.right_box.addWidget(Note(
                "info", "A per-volume result needs a density to reach a mass basis",
                "It is the density of the air-dried sample sieved to 2 mm, as "
                "scooped in the laboratory — not the bulk density of the field "
                "soil, whose structure the sieving destroyed.",
                "Choose how it is obtained on the Setup page."))

    def _set_unit(self, key: str, unit_id: str | None) -> None:
        project = self.state.project
        if unit_id:
            project.units[key] = unit_id
        else:
            project.units.pop(key, None)
        if project.unit_preset and un.preset(project.unit_preset) is not None:
            expected = un.preset(project.unit_preset).units.get(key)
            if expected != unit_id:
                project.unit_preset = None      # edited away from the preset
        self.state.result = None
        self.state.touch("data")
        self.refresh(rebuild_panel=False)
        # The panel carries state derived from this choice -- the preset name
        # and the note explaining a non-template unit -- so it has to be built
        # again. Deferred by one event loop turn because the dropdown that just
        # fired this is inside the panel, and destroying a widget from its own
        # signal handler is how Qt crashes.
        QTimer.singleShot(0, self._rebuild_mapping_panel)

    def _apply_preset(self, preset_id: str | None) -> None:
        preset = un.preset(preset_id) if preset_id else None
        project = self.state.project
        if preset is None:
            project.unit_preset = None
            return
        project.unit_preset = preset.id
        for key in list(self._units):
            if key in preset.units:
                project.units[key] = preset.units[key]
        self.state.result = None
        self.state.touch("data")
        self.refresh()

    def _index_of(self, target: str | None, targets: list[str]) -> int:
        if not target:
            return 0
        for index, label in enumerate(targets):
            if label.split("  ·  ")[0] == target:
                return index
        return 0

    def _remap(self, source: str, selector: QComboBox) -> None:
        label = selector.currentText()
        target = None if label == IGNORE else label.split("  ·  ")[0]
        report = self.state.import_report
        if report is None:
            return
        for mapping in report.mappings:
            if mapping.source == source:
                mapping.target = target
                mapping.confidence = "manual"
            elif mapping.target == target and target is not None:
                mapping.target = None
                other = self._selectors.get(mapping.source)
                if other:
                    other.blockSignals(True)
                    other.setCurrentIndex(0)
                    other.blockSignals(False)
        project = self.state.project
        project.mapped = importer.apply_mapping(report.original, report.mappings)
        project.column_mapping = {m.source: m.target for m in report.mappings}
        project.declare_units({m.target: m.unit for m in report.mappings
                               if m.target and m.unit})
        self.state.result = None
        self.state.touch("data")
        self.refresh(rebuild_panel=False)

    # ------------------------------------------------------------- refresh

    def refresh(self, rebuild_panel: bool = True) -> None:
        project = self.state.project
        has_data = project.has_data
        self.drop.setVisible(not has_data)
        self.splitter.setVisible(has_data)
        self.replace_button.setVisible(has_data)
        self.next_button.setEnabled(has_data)

        if rebuild_panel:
            self._rebuild_mapping_panel()

        if not has_data:
            self.summary_label.setText("")
            self.check_summary.setText("")
            return

        highlight = self._run_check()
        self.raw_table.set_frame(project.raw if project.raw is not None else pd.DataFrame())
        self.mapped_table.set_frame(project.mapped, highlight)

        indicators = [i.label for i in INDICATORS if i.key in project.mapped.columns]
        source = Path(project.source_file).name if project.source_file else "typed in"
        self.summary_label.setText(
            f"{len(project.mapped)} rows from {source}"
            + (f", sheet '{project.source_sheet}'" if project.source_sheet else "")
            + f"  ·  {len(indicators)} indicators recognised: {', '.join(indicators)}")

    def _run_check(self) -> dict[tuple[int, str], str]:
        project = self.state.project
        index = project.site_index()
        report = check(project.mapped, project.factors.as_dict(),
                       project.weights, project.model_id,
                       site_factors=project.selections(index.names)
                       if project.per_site else None,
                       site_index=index, units=project.units,
                       question_open=project.site_question_open())
        self.state.check_report = report

        highlight: dict[tuple[int, str], str] = {}
        for finding in report.findings:
            if finding.severity not in ("error", "warning") or not finding.scope:
                continue
            for row in finding.rows:
                position = project.mapped.index.get_loc(row) if row in project.mapped.index else None
                if position is not None:
                    highlight[(position, finding.scope)] = finding.severity

        counts = (len(report.errors), len(report.warnings))
        if counts[0]:
            self.check_summary.setText(
                f"{counts[0]} problem(s) block the analysis, {counts[1]} to review. "
                "They are listed on the Analysis page.")
            self.check_summary.setStyleSheet(f"font-size:11.5px;color:{theme.ERROR};")
        elif counts[1]:
            self.check_summary.setText(f"Data looks usable; {counts[1]} point(s) to review.")
            self.check_summary.setStyleSheet(f"font-size:11.5px;color:{theme.WARNING};")
        else:
            self.check_summary.setText("Data checks passed.")
            self.check_summary.setStyleSheet(f"font-size:11.5px;color:{theme.ACCENT};")
        return highlight
