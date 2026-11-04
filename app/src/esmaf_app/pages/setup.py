"""Setup: the decisions that tune the equations to this site.

Everything here is a scientific choice rather than a measurement, so each
control carries the reason it matters and the list of indicators it moves, and
nothing arrives pre-selected. The page is one continuous scroll rather than a
set of tabs: factor classes hidden behind a tab someone never opens are factor
classes chosen by accident.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDoubleSpinBox,
                               QFrame, QHBoxLayout, QLabel, QPushButton,
                               QRadioButton, QScrollArea, QVBoxLayout, QWidget)

from esmaf_core import factors as fx
from esmaf_core import units as un
from esmaf_core.indicators import (BY_KEY, COMPONENT_LABELS, COMPONENTS,
                                   INDICATORS, indicators_for)
from esmaf_core.models import load_model
from esmaf_core.parameters import SiteFactors
from esmaf_core.weights import SCHEME_EXPLANATIONS, SCHEME_LABELS, apply

from .. import theme
from ..state import AppState
from ..widgets import (Note, clear, hairline, hint, lead, panel, section, title)

NOT_SELECTED = "— choose one —"


class FactorCard(QFrame):
    """One factor class: the question, the consequence, and the choice."""

    def __init__(self, number: int, factor: fx.Factor, current: int | None,
                 used: list[str], on_change, texture_classes: int,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.factor = factor
        box = QVBoxLayout(self)
        box.setContentsMargins(15, 13, 15, 13)
        box.setSpacing(7)

        header = QHBoxLayout()
        header.setSpacing(9)
        index = QLabel(str(number))
        index.setFixedWidth(22)
        index.setAlignment(Qt.AlignmentFlag.AlignCenter)
        index.setStyleSheet(
            f"font-size:11px;font-weight:700;color:white;background:{theme.RAIL};"
            "border-radius:11px;padding:3px 0;")
        head = QLabel(factor.label)
        head.setStyleSheet(f"font-size:13px;font-weight:600;color:{theme.INK};")
        self.state_mark = QLabel()
        self.state_mark.setAlignment(Qt.AlignmentFlag.AlignRight
                                     | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(index)
        header.addWidget(head)
        header.addStretch(1)
        header.addWidget(self.state_mark)
        box.addLayout(header)

        question = QLabel(factor.question)
        question.setWordWrap(True)
        question.setMinimumWidth(1)
        question.setStyleSheet(f"font-size:12px;color:{theme.INK};")
        box.addWidget(question)

        self.selector = QComboBox()
        self.selector.addItem(NOT_SELECTED, None)
        for option in factor.options:
            if factor.key == "texture" and option.code > texture_classes:
                continue
            self.selector.addItem(f"{option.code} — {option.label}", option.code)
        if current is not None:
            position = self.selector.findData(current)
            if position >= 0:
                self.selector.setCurrentIndex(position)
        self.selector.currentIndexChanged.connect(self._changed)
        self._on_change = on_change
        box.addWidget(self.selector)

        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setMinimumWidth(1)
        self.detail.setStyleSheet(f"font-size:11.5px;color:{theme.INK_SOFT};")
        box.addWidget(self.detail)

        box.addWidget(hairline())
        why = QLabel(f"<b>Why it matters.</b> {factor.why}")
        why.setWordWrap(True)
        why.setMinimumWidth(1)
        why.setStyleSheet(f"font-size:11.5px;color:{theme.INK_SOFT};")
        box.addWidget(why)

        if used:
            affected = QLabel("Affects: " + ", ".join(used))
            affected.setWordWrap(True)
            affected.setMinimumWidth(1)
            affected.setStyleSheet(f"font-size:11px;color:{theme.INK_FAINT};")
            box.addWidget(affected)
        else:
            spare = QLabel("No indicator in this dataset uses it, but it is part "
                           "of the site description and is recorded with the result.")
            spare.setWordWrap(True)
            spare.setMinimumWidth(1)
            spare.setStyleSheet(f"font-size:11px;color:{theme.INK_FAINT};")
            box.addWidget(spare)

        if factor.reference:
            source = QLabel(factor.reference)
            source.setStyleSheet(f"font-size:10.5px;color:{theme.INK_FAINT};")
            box.addWidget(source)

        self._refresh_state()

    def _changed(self) -> None:
        self._refresh_state()
        self._on_change(self.factor.key, self.selector.currentData())

    def _refresh_state(self) -> None:
        code = self.selector.currentData()
        if code is None:
            self.detail.setText("")
            self.state_mark.setText("not chosen")
            self.state_mark.setStyleSheet(
                f"font-size:11px;font-weight:600;color:{theme.ERROR};")
            self.setStyleSheet(
                f"QFrame#panel {{ border: 1px solid {theme.ERROR}; }}")
            return
        try:
            self.detail.setText(self.factor.option(code).detail)
        except KeyError:
            self.detail.setText("")
        self.state_mark.setText("✓")
        self.state_mark.setStyleSheet(
            f"font-size:13px;font-weight:700;color:{theme.ACCENT};")
        self.setStyleSheet("")

    @property
    def chosen(self) -> bool:
        return self.selector.currentData() is not None


class SetupPage(QWidget):
    def __init__(self, state: AppState, go_to, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.state = state
        self.go_to = go_to
        self._cards: dict[str, FactorCard] = {}
        self._current_site: str | None = None
        self._weight_boxes: dict[str, QDoubleSpinBox] = {}
        self._component_boxes: dict[str, QDoubleSpinBox] = {}
        self._total_lines: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 26, 34, 16)
        layout.setSpacing(12)

        layout.addWidget(title("Setup"))
        layout.addWidget(lead(
            "How each site should be characterised, and how much each indicator "
            "should count. These are your decisions, not measurements. All "
            "eleven factor classes have to be chosen — for every site in the "
            "file — before the analysis can run, and none of them starts with "
            "a value."))

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("page")
        self.scroll.setWidget(body)
        self.box = QVBoxLayout(body)
        self.box.setContentsMargins(2, 4, 14, 8)
        self.box.setSpacing(12)
        layout.addWidget(self.scroll, 1)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setMinimumWidth(1)
        footer.addWidget(self.status, 1)
        self.jump_button = QPushButton("Go to the next one")
        self.jump_button.clicked.connect(self._jump_to_missing)
        footer.addWidget(self.jump_button)
        self.next_button = QPushButton("Continue to analysis")
        self.next_button.setObjectName("primary")
        self.next_button.clicked.connect(lambda: self.go_to("analysis"))
        footer.addWidget(self.next_button)
        layout.addLayout(footer)

        state.project_changed.connect(self.refresh)
        state.data_changed.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------- helpers

    def _available_indicators(self) -> set[str]:
        project = self.state.project
        if not project.has_data:
            return set()
        return {i.key for i in INDICATORS if i.key in project.mapped.columns} \
            - project.weights.excluded

    # ---------------------------------------------------------------- sites

    def _sites(self):
        return self.state.project.site_index()

    def _editing(self) -> str:
        """The site whose description the cards below are editing."""
        names = self._sites().names
        if not self.state.project.per_site or not names:
            return ""
        if self._current_site not in names:
            self._current_site = next(
                (n for n in names
                 if not self.state.project.factors_for(n).complete), names[0])
        return self._current_site

    def _current_factors(self) -> SiteFactors:
        site = self._editing()
        return self.state.project.factors_for(site) if site \
            else self.state.project.factors

    def _set_factor(self, key: str, code: int | None) -> None:
        project = self.state.project
        site = self._editing()
        updated = SiteFactors(**{**self._current_factors().as_dict(), key: code})
        if site:
            project.site_factors[site] = updated
        else:
            project.factors = updated
        self.state.result = None
        self.state.touch("setup")
        self._refresh_status()

    def _set_mode(self, per_site: bool) -> None:
        project = self.state.project
        if project.per_site is per_site:
            return
        project.per_site = per_site
        if per_site and not project.site_factors and project.factors.complete:
            # Carrying the shared description over as a starting point would
            # be a default in disguise, so each site starts empty instead --
            # but the description that was already made stays available
            # through "copy from", one click away and named.
            pass
        self.state.result = None
        self.state.touch("setup")
        self.refresh()

    def _pick_site(self, name: str) -> None:
        self._current_site = name
        self.refresh()

    def _merge_sites(self, first: str, second: str) -> None:
        project = self.state.project
        project.site_merges.append([first, second])
        project.site_factors.pop(second, None)
        self._current_site = None
        self.state.result = None
        self.state.touch("setup")
        self.refresh()

    def _copy_from(self, source: str) -> None:
        target = self._editing()
        if not target or source == target:
            return
        self.state.project.site_factors[target] = SiteFactors(
            **self.state.project.factors_for(source).as_dict())
        self.state.result = None
        self.state.touch("setup")
        self.refresh()

    def _jump_to_missing(self) -> None:
        for factor in fx.FACTORS:
            card = self._cards.get(factor.key)
            if card is not None and not card.chosen:
                self.scroll.ensureWidgetVisible(card, 0, 40)
                card.selector.setFocus()
                return
        project = self.state.project
        if project.per_site:
            for name in self._sites().names:
                if not project.factors_for(name).complete:
                    self._pick_site(name)
                    return
        self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum())

    # --------------------------------------------------------------- build

    def refresh(self) -> None:
        clear(self.box)
        self._cards.clear()
        self._weight_boxes.clear()
        self._total_lines.clear()
        self._component_boxes.clear()

        available = self._available_indicators()
        texture_classes = load_model(self.state.project.model_id).texture_classes
        self._build_sites()
        if self.state.project.site_question_open():
            # Showing eleven menus before it is known whose soil they describe
            # would invite someone to fill them in for the wrong place.
            self.box.addStretch(1)
            self._refresh_status()
            return
        site = self._editing()
        current = self._current_factors().as_dict()

        self._build_density()

        heading = "Factor classes"
        if site:
            heading = f"Factor classes for {site}"
        self.box.addWidget(section(heading))

        number = 0
        for group, group_label in fx.GROUPS:
            self.box.addWidget(section(group_label))
            for factor in fx.factors_in(group):
                number += 1
                used = [BY_KEY[k].label for k in factor.affects if k in available]
                card = FactorCard(number, factor, current.get(factor.key), used,
                                  self._set_factor, texture_classes)
                self._cards[factor.key] = card
                self.box.addWidget(card)

        self.box.addWidget(section("Weighting"))
        self._build_weights()
        self.box.addStretch(1)
        self._refresh_status()

    def _build_sites(self) -> None:
        """Ask, once, whether the places in this file share a description.

        The question only appears when the file actually holds more than one
        site. Neither answer is pre-selected: assuming that several farms share
        a soil would put a scientific claim in the application's mouth, and
        assuming they differ would make a single-farm user describe the same
        place several times.
        """
        project = self.state.project
        index = self._sites()
        if not index.from_column or not index.several:
            return

        self.box.addWidget(section("Sites in this file"))
        frame, inner = panel(15, 8)
        summary = QLabel(
            f"This spreadsheet holds <b>{len(index.sites)} sites</b>: "
            + ", ".join(f"{s.name} ({s.rows})" for s in index.sites)
            + ". The number in brackets is how many samples came from each.")
        summary.setWordWrap(True)
        summary.setMinimumWidth(1)
        summary.setStyleSheet(f"font-size:12px;color:{theme.INK};")
        inner.addWidget(summary)
        for note in index.spelling_notes():
            inner.addWidget(hint(note))
        inner.addWidget(hairline())

        if project.per_site is None:
            inner.addWidget(Note(
                "warning", "Which of these is true?",
                "Nothing is assumed here. Applying one description to several "
                "places, or describing each separately, is a decision about "
                "the places — so it is yours to make, and the analysis waits "
                "for it."))

        self.mode_group = QButtonGroup(self)
        for per_site, label, explanation in (
            (False, "All sites share the same factor classes",
             "Same texture, inherent organic matter, climate, relief, "
             "mineralogy, weathering and analytical methods. One description "
             "is applied to every sample."),
            (True, "The sites have different factor classes",
             "Each site is described on its own, and its samples are scored "
             "against the curves its own classes produce. Nothing is carried "
             "over from one site to another."),
        ):
            button = QRadioButton(label)
            button.setChecked(project.per_site is per_site)
            self.mode_group.addButton(button)
            button.toggled.connect(
                lambda checked, value=per_site:
                    self._set_mode(value) if checked else None)
            inner.addWidget(button)
            text = QLabel(explanation)
            text.setWordWrap(True)
            text.setMinimumWidth(1)
            text.setStyleSheet(
                f"font-size:11.5px;color:{theme.INK_SOFT};padding-left:22px;")
            inner.addWidget(text)
        self.box.addWidget(frame)

        for suggestion in index.suggestions:
            note = Note(
                "warning",
                f"'{suggestion.first}' and '{suggestion.second}' are spelled "
                "almost the same",
                "They are being treated as two places, each needing its own "
                "description, because only you can say whether they are one.",
                "")
            row = QHBoxLayout()
            row.addStretch(1)
            join = QPushButton("These are the same site")
            join.clicked.connect(
                lambda _=False, a=suggestion.first, b=suggestion.second:
                    self._merge_sites(a, b))
            row.addWidget(join)
            note.layout().addLayout(row)
            self.box.addWidget(note)

        if not project.per_site:
            return

        frame, inner = panel(15, 8)
        head = QLabel("Which site are you describing?")
        head.setStyleSheet(f"font-size:12.5px;font-weight:600;color:{theme.INK};")
        inner.addWidget(head)
        picker = QComboBox()
        for name in index.names:
            missing = len(project.factors_for(name).missing)
            mark = "✓" if not missing else f"{11 - missing} of 11"
            picker.addItem(f"{name}   —   {mark}", name)
        position = picker.findData(self._editing())
        if position >= 0:
            picker.setCurrentIndex(position)
        picker.currentIndexChanged.connect(
            lambda: self._pick_site(picker.currentData()))
        inner.addWidget(picker)

        described = [n for n in index.names
                     if n != self._editing()
                     and project.factors_for(n).complete]
        if described:
            row = QHBoxLayout()
            row.setSpacing(8)
            label = QLabel("Start from a site already described:")
            label.setStyleSheet(f"font-size:11.5px;color:{theme.INK_SOFT};")
            source = QComboBox()
            for name in described:
                source.addItem(name, name)
            copy = QPushButton("Copy its classes here")
            copy.clicked.connect(lambda: self._copy_from(source.currentData()))
            row.addWidget(label)
            row.addWidget(source, 1)
            row.addWidget(copy)
            inner.addLayout(row)
            inner.addWidget(hint(
                "Copying fills this site's eleven classes with that site's. "
                "Check each one afterwards — the copy is a starting point, not "
                "a statement that the two soils are the same."))
        self.box.addWidget(frame)

    def _build_density(self) -> None:
        """How a per-volume result reaches the mass basis the curves use.

        Only asked when some column was actually declared per volume. The
        density involved is the one of the sieved laboratory sample, which is
        why it can be assumed to be 1 at all -- the field bulk density never
        could be.
        """
        project = self.state.project
        if not project.uses_volume_basis():
            return

        volumetric = [BY_KEY[k].label for k in un.needs_density(project.units)]
        self.box.addWidget(section("Density of the sieved sample"))
        frame, inner = panel(15, 8)
        explain = QLabel(
            "Declared per volume of soil: <b>" + ", ".join(volumetric) + "</b>. "
            "To reach the mass basis the scoring curves use, each value is "
            "divided by the density of the air-dried sample sieved to 2 mm, as "
            "scooped in the laboratory. That is not the bulk density of the "
            "field soil: sieving destroys the structure bulk density "
            "describes, and the two differ by up to 70 %.")
        explain.setWordWrap(True)
        explain.setMinimumWidth(1)
        explain.setStyleSheet(f"font-size:12px;color:{theme.INK};")
        inner.addWidget(explain)
        inner.addWidget(hairline())

        self.density_group = QButtonGroup(self)
        for rule, (label_text, detail) in un.DENSITY_RULES.items():
            button = QRadioButton(label_text)
            button.setChecked(project.density_rule == rule)
            self.density_group.addButton(button)
            button.toggled.connect(
                lambda checked, value=rule:
                    self._set_density_rule(value) if checked else None)
            inner.addWidget(button)
            text = QLabel(detail)
            text.setWordWrap(True)
            text.setMinimumWidth(1)
            text.setStyleSheet(
                f"font-size:11.5px;color:{theme.INK_SOFT};padding-left:22px;")
            inner.addWidget(text)

        if project.density_rule == "by_texture":
            model = load_model(project.model_id)
            table = model.tables.get("sieved_density", {}).get("texture", {})
            names = self._sites().names
            lines = []
            for name in names:
                texture = project.factors_for(name).texture
                if texture is None:
                    how = "waiting for the texture class"
                else:
                    _, how = un.sieved_density(model, project.density_rule, texture)
                lines.append(f"{name}: {how}" if len(names) > 1 else how)
            inner.addWidget(hint("Applied: " + "; ".join(lines) + "."))
            inner.addWidget(hint(
                "Table: " + ", ".join(f"class {k} = {v}" for k, v in
                                      sorted(table.items())) + " kg dm-3. It is "
                "part of the calculation model, recorded with every result, and "
                "meant to be calibrated where a laboratory publishes its own."))
        self.box.addWidget(frame)

    def _set_density_rule(self, rule: str) -> None:
        if self.state.project.density_rule == rule:
            return
        self.state.project.density_rule = rule
        self.state.result = None
        self.state.touch("setup")
        self.refresh()

    def _build_weights(self) -> None:
        config = self.state.project.weights
        frame, inner = panel(15, 8)
        self.scheme_group = QButtonGroup(self)
        for scheme in ("equal_components", "equal_indicators", "custom"):
            button = QRadioButton(SCHEME_LABELS[scheme])
            button.setChecked(config.scheme == scheme)
            self.scheme_group.addButton(button)
            button.toggled.connect(
                lambda checked, s=scheme: self._set_scheme(s) if checked else None)
            inner.addWidget(button)
            explanation = QLabel(SCHEME_EXPLANATIONS[scheme])
            explanation.setWordWrap(True)
            explanation.setMinimumWidth(1)
            explanation.setStyleSheet(
                f"font-size:11.5px;color:{theme.INK_SOFT};padding-left:22px;")
            inner.addWidget(explanation)
        self.box.addWidget(frame)

        available = self._available_indicators()
        if config.scheme == "custom":
            for component in COMPONENTS:
                members = [i for i in indicators_for(component) if i.key in available]
                if not members:
                    continue
                frame, inner = panel(15, 6)
                head = QLabel(
                    f"{COMPONENT_LABELS[component]} indicator weights "
                    f"— must sum to 100 % to calculate the weighted component")
                head.setWordWrap(True)
                head.setMinimumWidth(1)
                head.setStyleSheet(
                    f"font-size:12.5px;font-weight:600;color:{theme.INK};")
                inner.addWidget(head)
                inner.addWidget(self._total_line(
                    component,
                    sum(config.indicator_weights.get(i.key, 0.0) for i in members),
                    f"{COMPONENT_LABELS[component].lower()} score"))
                for indicator in members:
                    row = QHBoxLayout()
                    name = QLabel(indicator.label)
                    name.setStyleSheet(f"font-size:11.5px;color:{theme.INK};")
                    spin = QDoubleSpinBox()
                    spin.setRange(0, 100)
                    spin.setDecimals(2)
                    spin.setSuffix(" %")
                    spin.setFixedWidth(96)
                    spin.setValue(config.indicator_weights.get(
                        indicator.key, 100.0 / len(members)))
                    spin.valueChanged.connect(
                        lambda value, key=indicator.key: self._set_weight(key, value))
                    self._weight_boxes[indicator.key] = spin
                    row.addWidget(name, 1)
                    row.addWidget(spin)
                    inner.addLayout(row)
                self.box.addWidget(frame)

            frame, inner = panel(15, 6)
            head = QLabel("Component weights across the index "
                          "— must sum to 100 % to calculate the weighted "
                          "soil health index")
            head.setWordWrap(True)
            head.setMinimumWidth(1)
            head.setStyleSheet(f"font-size:12.5px;font-weight:600;color:{theme.INK};")
            inner.addWidget(head)
            live = [c for c in COMPONENTS
                    if any(i.key in available for i in indicators_for(c))]
            inner.addWidget(self._total_line(
                "__components__",
                sum(config.component_weights.get(c, 0.0) for c in live),
                "soil health index"))
            if len(live) < len(COMPONENTS):
                inner.addWidget(hint(
                    "Only the components this dataset can compute are listed. "
                    + ", ".join(COMPONENT_LABELS[c] for c in COMPONENTS
                                if c not in live)
                    + " has no indicator here, so a weight for it would change "
                      "nothing."))
            for component in live:
                row = QHBoxLayout()
                name = QLabel(COMPONENT_LABELS[component])
                name.setStyleSheet(f"font-size:11.5px;color:{theme.INK};")
                spin = QDoubleSpinBox()
                spin.setRange(0, 100)
                spin.setDecimals(2)
                spin.setSuffix(" %")
                spin.setFixedWidth(96)
                spin.setValue(config.component_weights.get(component, 100.0 / 3))
                spin.valueChanged.connect(
                    lambda value, key=component: self._set_component_weight(key, value))
                self._component_boxes[component] = spin
                row.addWidget(name, 1)
                row.addWidget(spin)
                inner.addLayout(row)
            self.box.addWidget(frame)

        if available:
            applied = apply(config, available)
            frame, inner = panel(15, 5)
            head = QLabel("What each indicator will contribute")
            head.setStyleSheet(f"font-size:12.5px;font-weight:600;color:{theme.INK};")
            inner.addWidget(head)
            inner.addWidget(hint(
                "Shares are renormalised over the indicators present in this "
                "dataset, so an unmeasured indicator does not lower a score."))
            for component in COMPONENTS:
                if component not in applied.component:
                    continue
                share = applied.component[component]
                line = QLabel(f"{COMPONENT_LABELS[component]} — "
                              f"{share * 100:.1f} % of the index")
                line.setStyleSheet(
                    f"font-size:12px;font-weight:600;color:{theme.INK};")
                inner.addWidget(line)
                for indicator in indicators_for(component):
                    weight = applied.indicator.get(indicator.key)
                    if weight is None:
                        continue
                    detail = QLabel(
                        f"     {indicator.label}: {weight * 100:.1f} % of the "
                        f"component, {weight * share * 100:.1f} % of the index")
                    detail.setWordWrap(True)
                    detail.setMinimumWidth(1)
                    detail.setStyleSheet(f"font-size:11px;color:{theme.INK_SOFT};")
                    inner.addWidget(detail)
            missing = [BY_KEY[k].label for k in applied.missing_indicators]
            if missing:
                inner.addWidget(hint("Not in this dataset: " + ", ".join(missing)))
            self.box.addWidget(frame)

        for problem in config.validate(available):
            self.box.addWidget(Note(
                "error", problem,
                "Weights define proportions; a total other than 100 % is ambiguous.",
                "Adjust the values, or pick an equal-weight scheme."))

    # ------------------------------------------------------------- weights

    def _total_line(self, key: str, total: float, what: str) -> QLabel:
        """The running total, in green when it closes and red when it does not."""
        line = QLabel()
        line.setWordWrap(True)
        line.setMinimumWidth(1)
        self._write_total(line, total, what)
        self._total_lines[key] = line
        return line

    @staticmethod
    def _write_total(line: QLabel, total: float, what: str) -> None:
        closed = abs(total - 100.0) <= 0.01
        line.setText(
            f"Total {total:.2f} %"
            + ("" if closed else f" — {100 - total:+.2f} % to go")
            + (f"  ·  these proportions give the weighted {what}" if closed else ""))
        line.setStyleSheet(
            f"font-size:11px;font-weight:600;"
            f"color:{theme.ACCENT if closed else theme.ERROR};")

    def _set_scheme(self, scheme: str) -> None:
        config = self.state.project.weights
        if config.scheme == scheme:
            return
        config.scheme = scheme
        if scheme == "custom":
            # Seeded over the indicators this dataset has, so the boxes the
            # user is shown already add up to the 100 % they are asked for.
            available = self._available_indicators()
            if not config.indicator_weights:
                config.indicator_weights = config.seed_indicator_weights(available)
                config.component_weights = config.seed_component_weights(available)
            else:
                seed = config.seed_indicator_weights(available)
                for component in COMPONENTS:
                    members = config.members(component, available)
                    if members and not any(config.indicator_weights.get(k)
                                           for k in members):
                        for key in members:
                            config.indicator_weights[key] = seed[key]
        self.state.result = None
        self.state.touch("setup")
        self.refresh()

    def _set_weight(self, key: str, value: float) -> None:
        self.state.project.weights.indicator_weights[key] = value
        self.state.result = None
        self.state.touch("setup")
        self._refresh_totals()

    def _set_component_weight(self, key: str, value: float) -> None:
        self.state.project.weights.component_weights[key] = value
        self.state.result = None
        self.state.touch("setup")
        self._refresh_totals()

    def _refresh_totals(self) -> None:
        """Update the running totals without rebuilding the boxes underfoot.

        A spin box must survive the signal it just emitted, so the panel is not
        rebuilt here; only the text that depends on the new value is rewritten.
        """
        config = self.state.project.weights
        available = self._available_indicators()
        for component, line in self._total_lines.items():
            if component == "__components__":
                live = [c for c in COMPONENTS if config.members(c, available)]
                self._write_total(
                    line, sum(config.component_weights.get(c, 0.0) for c in live),
                    "soil health index")
            else:
                members = config.members(component, available)
                self._write_total(
                    line, sum(config.indicator_weights.get(k, 0.0) for k in members),
                    f"{COMPONENT_LABELS[component].lower()} score")
        self._refresh_status()

    # -------------------------------------------------------------- status

    def _refresh_status(self) -> None:
        project = self.state.project
        per = len(fx.FACTORS)
        names = self._sites().names
        site = self._editing()
        missing = self._current_factors().missing
        chosen = per - len(missing)
        problems = project.weights.validate(project.available_indicators())
        elsewhere = [n for n in names
                     if n != site and not project.factors_for(n).complete] \
            if project.per_site else []
        unanswered = project.site_question_open()
        everything = (project.factors_complete(names) and not problems
                      and not unanswered)

        self.jump_button.setVisible(bool(missing) or bool(elsewhere))
        self.next_button.setEnabled(everything)

        here = f" for {site}" if site else ""
        if unanswered:
            self.status.setText(
                "<b>Say first whether the sites share the same factor "
                "classes.</b> Nothing is assumed.")
            self.status.setStyleSheet(f"font-size:11.5px;color:{theme.ERROR};")
            self.jump_button.setVisible(False)
            return
        if missing:
            labels = ", ".join(fx.BY_KEY[k].label for k in missing[:4])
            more = f" and {len(missing) - 4} more" if len(missing) > 4 else ""
            text = (f"<b>{chosen} of {per} factor classes chosen{here}.</b> "
                    f"Still to choose: {labels}{more}.")
            colour = theme.ERROR
        elif elsewhere:
            text = (f"<b>{site} is described.</b> Still to describe: "
                    + ", ".join(elsewhere[:3])
                    + (" …" if len(elsewhere) > 3 else "") + ".")
            colour = theme.ERROR
        elif problems:
            text, colour = problems[0], theme.ERROR
        elif project.per_site and len(names) > 1:
            text = (f"<b>All {len(names)} sites described</b>, {per} factor "
                    "classes each, and the weights are valid.")
            colour = theme.ACCENT
        else:
            text = (f"<b>All {per} factor classes chosen</b> and the weights "
                    "are valid.")
            colour = theme.ACCENT

        self.status.setText(text)
        self.status.setStyleSheet(f"font-size:11.5px;color:{colour};")
