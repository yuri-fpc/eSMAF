"""Reading a spreadsheet and working out what is in it.

The web version required a spreadsheet that already matched its expectations
exactly and reported a technical failure otherwise.  Here an unrecognised
column is a question to answer, not an error: the importer proposes a mapping,
says why, and leaves every proposal editable before anything is calculated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .indicators import (BY_KEY, CONTEXT_COLUMNS, INDICATORS, resolve_column,
                         suggest_column)

READABLE = {".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".txt"}


@dataclass
class ColumnMapping:
    source: str                       # header as found in the file
    target: str | None                # indicator key, context column, or None
    confidence: str                   # exact | fuzzy | none | manual
    suggestions: list[str] = field(default_factory=list)
    unit_note: str = ""
    #: The unit the header states, when it states one. A proposal, never an
    #: assumption: a column called simply "P" leaves this empty and the
    #: interface asks.
    unit: str | None = None

    @property
    def ignored(self) -> bool:
        return self.target is None


@dataclass
class ImportReport:
    frame: pd.DataFrame                       # data with canonical column names
    original: pd.DataFrame                    # exactly as read, never modified
    mappings: list[ColumnMapping]
    sheet: str | None = None
    source: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def recognised(self) -> list[ColumnMapping]:
        return [m for m in self.mappings if m.target]

    @property
    def unrecognised(self) -> list[ColumnMapping]:
        return [m for m in self.mappings if not m.target]

    @property
    def indicators_found(self) -> list[str]:
        return [m.target for m in self.mappings
                if m.target and m.target in BY_KEY]

    def describe(self) -> str:
        n_ind = len(self.indicators_found)
        return (f"{len(self.frame)} rows, {n_ind} indicator column"
                f"{'' if n_ind == 1 else 's'} recognised, "
                f"{len(self.unrecognised)} column"
                f"{'' if len(self.unrecognised) == 1 else 's'} not recognised")


def list_sheets(path: str | Path) -> list[str]:
    path = Path(path)
    if path.suffix.lower() in {".csv", ".tsv", ".txt"}:
        return []
    with pd.ExcelFile(path) as book:
        return list(book.sheet_names)


def read_file(path: str | Path, sheet: str | int | None = None,
              header_row: int = 0) -> tuple[pd.DataFrame, str | None]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in READABLE:
        raise UnsupportedFile(
            f"'{path.name}' has the extension '{suffix}', which eSMAF cannot read. "
            f"Supported: {', '.join(sorted(READABLE))}."
        )
    if suffix in {".csv", ".tsv", ".txt"}:
        separator = "\t" if suffix == ".tsv" else None
        frame = pd.read_csv(path, sep=separator, engine="python", header=header_row)
        return frame, None
    with pd.ExcelFile(path) as book:
        chosen = sheet if sheet is not None else book.sheet_names[0]
        frame = book.parse(chosen, header=header_row)
    return frame, str(chosen)


def propose_mapping(frame: pd.DataFrame) -> list[ColumnMapping]:
    """Match every header against the indicator and context registries."""
    mappings: list[ColumnMapping] = []
    claimed: set[str] = set()

    for header in frame.columns:
        name = str(header).strip()
        target = resolve_column(name)
        if target and target not in claimed:
            claimed.add(target)
            mappings.append(ColumnMapping(
                source=name, target=target, confidence="exact",
                unit_note=_unit_note(target), unit=_unit_from_header(name, target),
            ))
            continue
        if target and target in claimed:
            mappings.append(ColumnMapping(
                source=name, target=None, confidence="none",
                suggestions=[],
                unit_note=(f"'{name}' maps to the same variable as an earlier "
                           "column; only the first was kept."),
            ))
            continue
        suggestions = [s for s in suggest_column(name)
                       if resolve_column(s) not in claimed]
        mappings.append(ColumnMapping(
            source=name, target=None,
            confidence="fuzzy" if suggestions else "none",
            suggestions=suggestions,
        ))
    return mappings


def apply_mapping(frame: pd.DataFrame,
                  mappings: list[ColumnMapping]) -> pd.DataFrame:
    """Build the canonical frame the engine expects.

    Values are carried across exactly as the user supplied them. Converting
    them here would be too early: putting a result reported per volume onto a
    mass basis needs the texture class of the site it came from, and the site
    has not been described yet. The declared unit travels with the project and
    the conversion happens once, in the engine, where it can be recorded.
    """
    out = pd.DataFrame(index=frame.index)
    for mapping in mappings:
        if not mapping.target:
            continue
        series = frame[mapping.source]
        if mapping.target in BY_KEY:
            series = pd.to_numeric(series, errors="coerce")
        out[mapping.target] = series
    return out


def load(path: str | Path, sheet: str | int | None = None,
         header_row: int = 0) -> ImportReport:
    """Read a file and propose a full mapping in one call."""
    frame, sheet_name = read_file(path, sheet, header_row)
    frame = frame.dropna(how="all").dropna(axis=1, how="all")
    frame.columns = [str(c).strip() for c in frame.columns]
    mappings = propose_mapping(frame)
    canonical = apply_mapping(frame, mappings)
    notes: list[str] = []
    for mapping in mappings:
        if mapping.unit:
            from . import units as un
            notes.append(f"'{mapping.source}' states its unit: "
                         f"{un.label(mapping.target, mapping.unit)}.")
    return ImportReport(frame=canonical, original=frame, mappings=mappings,
                        sheet=sheet_name, source=str(path), notes=notes)


def _unit_note(target: str) -> str:
    indicator = BY_KEY.get(target)
    if indicator is None:
        return ""
    return f"expected in {indicator.unit}"


def _unit_from_header(name: str, target: str) -> str | None:
    """What unit the header states, if any. Delegated to the units registry."""
    from . import units as un

    return un.from_header(target, name)


class UnsupportedFile(ValueError):
    """Raised for a file extension the importer cannot read."""


TEMPLATE_COLUMNS: tuple[str, ...] = (
    *CONTEXT_COLUMNS,
    *(ind.canonical_column for ind in INDICATORS),
)


#: Shown as a cell note on the template headers that need more than a unit.
COLUMN_NOTES: dict[str, str] = {
    "site": (
        "Optional. The place each sample came from - a farm, a station, an "
        "experiment. Leave the whole column empty if every sample comes from "
        "one place.\n\n"
        "Samples from different places are scored with different factor "
        "classes: eSMAF asks you to describe each site once, and then uses "
        "each site's own soil, climate and method classes for its samples. "
        "That is what lets one file hold several places without biasing the "
        "scores.\n\n"
        "Spelling is tidied for you (case, accents, punctuation), but two "
        "genuinely different names stay two places until you say otherwise."
    ),
}


def write_template(path: str | Path, rows: int = 0) -> Path:
    """Write an empty eSMAF spreadsheet.

    One template, not three. The unit is written into the column header
    itself, so a file that leaves the laboratory carries its own units with
    it: shared with a colleague or reopened in five years, it still says what
    its numbers mean. A second sheet lists the alternatives eSMAF accepts, so
    someone working from a report in another unit can rename the header rather
    than convert by hand -- and whichever header arrives, the application asks
    for the unit to be confirmed before anything is scored.
    """
    from . import units as un

    path = Path(path)
    header_units = ["" for _ in CONTEXT_COLUMNS]
    header_units += [ind.unit for ind in INDICATORS]
    frame = pd.DataFrame(
        [header_units] + [[""] * len(TEMPLATE_COLUMNS) for _ in range(rows)],
        columns=list(TEMPLATE_COLUMNS),
    )
    if path.suffix.lower() == ".csv":
        frame.to_csv(path, index=False)
        return path

    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        frame.to_excel(writer, sheet_name="Data", index=False)
        book, sheet = writer.book, writer.sheets["Data"]
        head = book.add_format({"bold": True, "bg_color": "#E8EFE6", "border": 1})
        unit = book.add_format({"italic": True, "font_color": "#5A6B57"})
        for column, name in enumerate(TEMPLATE_COLUMNS):
            sheet.write(0, column, name, head)
            sheet.set_column(column, column, max(12, len(name) + 2))
            note = COLUMN_NOTES.get(name) or _unit_comment(name)
            if note:
                sheet.write_comment(0, column, note, {"width": 300, "height": 160})
        sheet.set_row(1, None, unit)
        sheet.freeze_panes(2, 0)

        guide = book.add_worksheet("Units")
        guide.set_column(0, 0, 30)
        guide.set_column(1, 1, 26)
        guide.set_column(2, 2, 34)
        guide.set_column(3, 3, 74)
        title = book.add_format({"bold": True, "font_size": 13,
                                 "font_color": "#1f3a2e"})
        wrap = book.add_format({"text_wrap": True, "valign": "top"})
        guide.write(0, 0, "Units eSMAF accepts", title)
        guide.write(1, 0,
                    "Write the unit into the column header, as the Data sheet "
                    "does, and eSMAF will read it. Whatever the header says, "
                    "the application asks you to confirm the unit before it "
                    "scores anything, and records the conversion it performed "
                    "with the result.", wrap)
        for column, label in enumerate(
                ("Indicator", "Header in the template", "Also accepted",
                 "What eSMAF does with it")):
            guide.write(3, column, label, head)
        line = 4
        for indicator in INDICATORS:
            choices = un.options(indicator.key)
            if not choices:
                continue
            guide.write(line, 0, indicator.label)
            guide.write(line, 1, indicator.canonical_column)
            guide.write(line, 2, choices[0].label)
            guide.write(line, 3, "The basis the scoring curve is defined on.", wrap)
            line += 1
            for alternative in choices[1:]:
                guide.write(line, 2, alternative.label)
                guide.write(line, 3, alternative.note, wrap)
                line += 1
    return path


def _unit_comment(header: str) -> str:
    """The cell note that says what unit a column is in, and what else fits."""
    from . import units as un

    target = resolve_column(header)
    if target is None or target not in un.UNITS:
        return ""
    choices = un.options(target)
    indicator = BY_KEY[target]
    lines = [f"{indicator.label}.",
             f"This template asks for {choices[0].label}, which is the basis "
             "the scoring curve is defined on."]
    if len(choices) > 1:
        lines.append("")
        lines.append("eSMAF also accepts:")
        lines += [f"  - {c.label}: {c.note}" for c in choices[1:]]
        lines.append("")
        lines.append("Whatever you supply, the application asks you to confirm "
                     "the unit before scoring and records what it converted.")
    return "\n".join(lines)
