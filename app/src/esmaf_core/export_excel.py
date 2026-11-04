"""Excel export.

The workbook is the analysis in full: what came in, what was computed, and
which settings produced it.  Raw data is never overwritten by scores -- the
sheets are layered so an error can be traced back to its source.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import factors as fx
from .engine import AnalysisResult
from .indicators import BY_KEY, COMPONENT_LABELS, COMPONENTS, CONTEXT_COLUMNS, INDICATORS
from .weights import SCHEME_EXPLANATIONS, SCHEME_LABELS

SHEETS = (
    "Analysis summary", "Raw data", "Processed data", "Indicator scores",
    "Component scores", "Soil health index", "Parameters", "Warnings",
)


def export(result: AnalysisResult, path: str | Path,
           project_name: str = "", description: str = "") -> Path:
    path = Path(path)
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        path = path.with_suffix(".xlsx")

    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        book = writer.book
        title = book.add_format({"bold": True, "font_size": 13, "font_color": "#1f3a2e"})
        head = book.add_format({"bold": True, "bg_color": "#E8EFE6", "border": 1,
                                "text_wrap": True, "valign": "top"})
        key = book.add_format({"bold": True, "valign": "top"})
        wrap = book.add_format({"text_wrap": True, "valign": "top"})
        score = book.add_format({"num_format": "0.00"})

        _summary(writer, result, project_name, description, title, key, wrap)

        if result.raw is not None:
            _table(writer, "Raw data", result.raw, head)

        context = [c for c in CONTEXT_COLUMNS if c in result.scores.columns]
        measured = [i.key for i in INDICATORS if i.key in result.scores.columns]
        _table(writer, "Processed data", result.scores[context + measured], head,
               note=("Values as they entered the equations, after unit conversion. "
                     "The Raw data sheet holds the file exactly as imported."))

        score_columns = result.score_columns()
        _table(writer, "Indicator scores", result.scores[context + score_columns],
               head, numeric=score_columns, numeric_format=score)

        component_columns = result.component_columns()
        if component_columns:
            _table(writer, "Component scores",
                   result.scores[context + component_columns], head,
                   numeric=component_columns, numeric_format=score)

        index_columns = [c for c in (result.index_column,) if c in result.scores.columns]
        if index_columns:
            _table(writer, "Soil health index",
                   result.scores[context + index_columns], head,
                   numeric=index_columns, numeric_format=score,
                   note=(f"{result.index_label}. "
                         + ("Complete index: all three components available."
                            if result.complete_index else
                            "PARTIAL index: at least one component was not available. "
                            "It is renormalised over the components present, so it "
                            "still ranges from 0 to 1, but it describes fewer soil "
                            "functions and is not comparable with a complete index.")))

        if not result.aggregated.empty:
            _table(writer, "Aggregated results", result.aggregated, head,
                   note=("Descriptive statistics by land use, management, crop and "
                         "depth. No significance testing has been performed: a "
                         "difference between two means here describes these samples "
                         "and is not evidence of an effect."))

        _parameters(writer, result, head, key, wrap, title)
        _warnings(writer, result, head, title, wrap)

    return path


def _summary(writer, result: AnalysisResult, project_name: str, description: str,
             title, key_fmt, wrap) -> None:
    sheet = writer.book.add_worksheet("Analysis summary")
    writer.sheets["Analysis summary"] = sheet
    sheet.set_column(0, 0, 34)
    sheet.set_column(1, 1, 78)
    sheet.write(0, 0, "eSMAF analysis summary", title)

    p = result.provenance
    rows: list[tuple[str, object]] = [
        ("Project", project_name or "(unnamed)"),
        ("Description", description or ""),
        ("", ""),
        ("Analysis date", p.get("analysis_datetime", "")),
        ("Software version", p.get("software_version", "")),
        ("Calculation model", f"{p.get('model_id')} - {p.get('model_label')}"),
        ("Model based on", p.get("model_based_on", "")),
        ("Crop database version", p.get("crop_db_version", "")),
        ("", ""),
        ("Samples", p.get("n_samples", "")),
        ("Sites", ", ".join(s.name for s in result.sites.sites)
                  if result.sites.from_column else "one (no site column)"),
        ("Crops", ", ".join(p.get("crops", []))),
        ("Indicators used", ", ".join(
            BY_KEY[k].label for k in p.get("indicators_used", []))),
        ("Indicators not available", ", ".join(
            BY_KEY[k].label for k in result.missing_indicators) or "none"),
        ("", ""),
        ("Index reported", result.index_label),
        ("Index is complete", "yes" if result.complete_index else
         "no - partial index, fewer soil functions"),
        ("Weighting scheme", p.get("weighting_scheme_label", "")),
        ("What that means", SCHEME_EXPLANATIONS.get(p.get("weighting_scheme", ""), "")),
    ]
    row = 2
    for label, value in rows:
        if label:
            sheet.write(row, 0, label, key_fmt)
            sheet.write(row, 1, value if value is not None else "", wrap)
        row += 1

    row += 1
    names = [site.name for site in result.sites.sites]
    for name in names:
        selection = result.factors_for(name).as_dict()
        sheet.write(row, 0,
                    f"Factor classes - {name}" if len(names) > 1
                    else "Factor classes", title)
        row += 1
        for factor in fx.FACTORS:
            code = selection.get(factor.key)
            try:
                label = factor.option(int(code)).label
            except (KeyError, ValueError, TypeError):
                label = "not selected" if code is None else str(code)
            sheet.write(row, 0, factor.label, key_fmt)
            sheet.write(row, 1, f"{code} - {label}" if code is not None else label,
                        wrap)
            row += 1
        row += 1
    from . import units as un
    declared = p.get("units_declared", {})
    if declared:
        sheet.write(row, 0, "Units as supplied", title)
        row += 1
        for key, unit_id in declared.items():
            native = un.DEFAULT_UNIT.get(key, "")
            sheet.write(row, 0, BY_KEY[key].label if key in BY_KEY else key, key_fmt)
            sheet.write(row, 1, f"{un.label(key, unit_id)}"
                        + ("" if unit_id == native
                           else f"  ->  converted to {un.label(key, native)}"), wrap)
            row += 1
        row += 1
    for record in p.get("unit_conversions", []):
        sheet.write(row, 0, "Conversion", key_fmt)
        sheet.write(row, 1, record["detail"], wrap)
        row += 1
    if p.get("unit_conversions"):
        row += 1

    for note in result.sites.spelling_notes():
        sheet.write(row, 0, "Site name", key_fmt)
        sheet.write(row, 1, note, wrap)
        row += 1

    row += 1
    sheet.write(row, 0, "Weights applied", title)
    row += 1
    sheet.write(row, 0, "Component", key_fmt)
    sheet.write(row, 1, "Share of the index / of its component", key_fmt)
    row += 1
    for component in COMPONENTS:
        share = p.get("component_weights", {}).get(component)
        if share is None:
            continue
        sheet.write(row, 0, COMPONENT_LABELS[component], key_fmt)
        sheet.write(row, 1, f"{share * 100:.2f} % of the index")
        row += 1
        for indicator in INDICATORS:
            if indicator.component != component:
                continue
            weight = p.get("indicator_weights", {}).get(indicator.key)
            if weight is None:
                continue
            sheet.write(row, 0, f"    {indicator.label}")
            sheet.write(row, 1, f"{weight * 100:.2f} % of the component "
                                f"({weight * share * 100:.2f} % of the index)")
            row += 1


def _table(writer, name: str, frame: pd.DataFrame, head, note: str = "",
           numeric: list[str] | None = None, numeric_format=None) -> None:
    start = 2 if note else 0
    frame.to_excel(writer, sheet_name=name[:31], index=False, startrow=start)
    sheet = writer.sheets[name[:31]]
    book = writer.book
    if note:
        sheet.merge_range(0, 0, 0, max(1, len(frame.columns) - 1), note,
                          book.add_format({"italic": True, "text_wrap": True,
                                           "font_color": "#52514e", "valign": "top"}))
        sheet.set_row(0, 30)
    for index, column in enumerate(frame.columns):
        sheet.write(start, index, _pretty(column), head)
        width = max(11, min(30, len(_pretty(column)) + 3))
        if numeric and column in numeric and numeric_format is not None:
            sheet.set_column(index, index, width, numeric_format)
        else:
            sheet.set_column(index, index, width)
    sheet.freeze_panes(start + 1, 0)
    if len(frame):
        sheet.autofilter(start, 0, start + len(frame), max(0, len(frame.columns) - 1))


def _parameters(writer, result: AnalysisResult, head, key, wrap, title) -> None:
    sheet = writer.book.add_worksheet("Parameters")
    writer.sheets["Parameters"] = sheet
    sheet.set_column(0, 0, 22)
    sheet.set_column(1, 1, 18)
    sheet.set_column(2, 2, 62)
    sheet.write(0, 0, "Resolved equation parameters, by site and crop", title)
    sheet.write(1, 0, "These are the coefficients the scoring equations were "
                      "evaluated with. Together with the factor classes and the "
                      "model version they are what makes this analysis reproducible. "
                      "With more than one site the same crop appears once per site, "
                      "because the site's classes change the coefficients.",
                wrap)
    row = 3
    several = result.several_sites
    for (site, crop), resolved in sorted(result.parameters.items()):
        sheet.write(row, 0, f"{site} — {crop}" if several else crop, key)
        row += 1
        sheet.write(row, 0, "Indicator", head)
        sheet.write(row, 1, "Parameter", head)
        sheet.write(row, 2, "Value", head)
        row += 1
        for indicator, values in resolved.values.items():
            if not isinstance(values, dict):
                continue
            for name, value in values.items():
                if isinstance(value, dict):
                    continue
                sheet.write(row, 0, indicator)
                sheet.write(row, 1, name)
                sheet.write(row, 2, value if isinstance(value, (int, float, str)) else str(value))
                row += 1
        row += 1


def _warnings(writer, result: AnalysisResult, head, title, wrap) -> None:
    sheet = writer.book.add_worksheet("Warnings")
    writer.sheets["Warnings"] = sheet
    sheet.set_column(0, 0, 110)
    sheet.write(0, 0, "Warnings raised during this analysis", title)
    if not result.warnings:
        sheet.write(2, 0, "None.")
        return
    for index, message in enumerate(result.warnings):
        sheet.write(2 + index, 0, message, wrap)


def _pretty(column: str) -> str:
    if column.endswith("_score"):
        key = column[:-6]
        if key == "WFPS_BiolAct":
            return "WFPS biological activity score"
        if key == "WFPS_EnvProtect":
            return "WFPS environmental protection score"
        indicator = BY_KEY.get(key)
        return f"{indicator.label} score" if indicator else column
    if column.endswith("_component"):
        return f"{COMPONENT_LABELS.get(column[:-10], column)} component"
    if column in BY_KEY:
        indicator = BY_KEY[column]
        return f"{indicator.label} ({indicator.unit})"
    return column.replace("_", " ").capitalize()
