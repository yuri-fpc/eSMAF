"""The PDF report.

The web version produced a short summary of the result.  Here the report is
the record of the analysis: what was measured, what was decided, what was
computed and what should be treated with caution.  Someone who was not in the
room should be able to read it and know how the number was produced.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether,
                                NextPageTemplate, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

from . import charts
from . import factors as fx
from .engine import AnalysisResult
from .indicators import BY_KEY, COMPONENT_LABELS, COMPONENTS, INDICATORS
from .weights import SCHEME_EXPLANATIONS

Detail = Literal["summary", "standard", "full"]

INK = colors.HexColor("#0b0b0b")
SOFT = colors.HexColor("#52514e")
RULE = colors.HexColor("#d8d7d3")
ACCENT = colors.HexColor("#1f3a2e")
WARN_BG = colors.HexColor("#fdf3e3")
INFO_BG = colors.HexColor("#eef4fb")

# --- page geometry ---------------------------------------------------------
# A result table can carry twenty-odd columns, and dividing the page evenly
# between them is what made the old report unreadable: every heading wrapped
# to three lines and the numbers sat in 6 mm gutters. Two things prevent that
# here. Wide tables get their own landscape pages, and column widths are
# measured from the text rather than assumed; if the columns still do not fit,
# the table continues below with the identifying columns repeated instead of
# being squeezed. Nothing is ever narrower than its own content.
MARGIN = 18 * mm
TOP_MARGIN = 16 * mm
BOTTOM_MARGIN = 18 * mm
PORTRAIT = A4
LANDSCAPE = landscape(A4)
PORTRAIT_WIDTH = PORTRAIT[0] - 2 * MARGIN      # 174 mm
LANDSCAPE_WIDTH = LANDSCAPE[0] - 2 * MARGIN    # 261 mm

CELL_FONT = "Helvetica"
CELL_FONT_BOLD = "Helvetica-Bold"
CELL_SIZE = 8.5
CELL_SIDE_PADDING = 4.0   # set explicitly: ReportLab defaults to 6 pt a side
CELL_PADDING = 2 * CELL_SIDE_PADDING + 2.0
MAX_KEY_WIDTH = 34 * mm   # a long crop name wraps rather than eating the page


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=20, leading=24,
                                textColor=ACCENT, alignment=TA_LEFT, spaceAfter=2),
        "subtitle": ParagraphStyle("st", parent=base["Normal"], fontSize=10.5,
                                   textColor=SOFT, spaceAfter=14),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=13, leading=16,
                             textColor=ACCENT, spaceBefore=16, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=11, leading=14,
                             textColor=INK, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9.5, leading=13.5,
                               textColor=INK, spaceAfter=6),
        "small": ParagraphStyle("s", parent=base["Normal"], fontSize=8, leading=11,
                                textColor=SOFT),
        "cell": ParagraphStyle("c", parent=base["Normal"], fontSize=8.5, leading=11.5),
        "cellhead": ParagraphStyle("ch", parent=base["Normal"], fontSize=8.5,
                                   leading=11.5, textColor=colors.white),
    }


@dataclass
class ReportOptions:
    detail: Detail = "standard"
    project_name: str = ""
    description: str = ""
    author: str = ""
    include_individual_results: bool = True
    max_individual_rows: int = 120


def build(result: AnalysisResult, path: str | Path,
          options: ReportOptions | None = None) -> Path:
    options = options or ReportOptions()
    path = Path(path)
    if path.suffix.lower() != ".pdf":
        path = path.with_suffix(".pdf")
    s = _styles()

    doc = _document(path, options)
    story: list = []
    p = result.provenance

    # ------------------------------------------------------------ heading
    story.append(Paragraph("Soil health assessment", s["title"]))
    story.append(Paragraph(
        f"{options.project_name or 'Untitled project'} &nbsp;·&nbsp; "
        f"generated {datetime.now().astimezone().strftime('%d %B %Y, %H:%M %Z')}",
        s["subtitle"]))
    if options.description:
        story.append(Paragraph(options.description, s["body"]))

    # ------------------------------------------------------------ headline
    index_values = result.scores[result.index_column].dropna()
    if len(index_values):
        headline = (f"<b>{result.index_label}: {index_values.mean():.2f}</b> "
                    f"across {result.n_samples} samples "
                    f"(range {index_values.min():.2f} to {index_values.max():.2f})")
        if not result.complete_index:
            headline += ("<br/><font color='#8a5a00'>This is a partial index. "
                         "It is renormalised over the components that were "
                         "available, so it still runs from 0 to 1, but it covers "
                         "fewer soil functions than a complete Soil Health Index "
                         "and the two should not be compared directly.</font>")
        story.append(_callout(headline, s, INFO_BG))

    # ------------------------------------------------------------- what/how
    story.append(Paragraph("1. What was analysed", s["h1"]))
    story.append(_kv_table([
        ("Samples", str(p.get("n_samples", ""))),
        ("Sites", ", ".join(site.name for site in result.sites.sites)
                  if result.sites.from_column else "one (no site column)"),
        ("Crops", ", ".join(p.get("crops", []))),
        ("Indicators used", ", ".join(BY_KEY[k].label for k in p.get("indicators_used", []))),
        ("Not available", ", ".join(BY_KEY[k].label for k in result.missing_indicators) or "none"),
        ("Index reported", f"{result.index_label} "
                           f"({'complete' if result.complete_index else 'partial'})"),
    ], s))

    story.append(Paragraph("2. Site characterisation (factor classes)", s["h1"]))
    story.append(Paragraph(
        "Factor classes adjust the scoring equations to the site. They are "
        "decisions made by the analyst, not measurements, and they change the "
        "scores substantially.", s["body"]))
    story.extend(_factor_section(result, s))

    # ---------------------------------------------------------------- units
    story.append(Paragraph("3. Units and conversions", s["h1"]))
    story.extend(_units_section(result, s))

    # -------------------------------------------------------------- weights
    story.append(Paragraph("4. Weighting", s["h1"]))
    story.append(Paragraph(
        f"<b>{p.get('weighting_scheme_label', '')}.</b> "
        f"{SCHEME_EXPLANATIONS.get(p.get('weighting_scheme', ''), '')}", s["body"]))
    fig = charts.weight_tree(
        {k: v for k, v in p.get("indicator_weights", {}).items()},
        p.get("component_weights", {}),
        charts.ChartContext("How weight flows to the index",
                            "The bar closes at 100 %. Each segment is one "
                            "indicator's share of the index: its weight within "
                            "its component, times that component's share."))
    story.append(_figure(fig, doc, height=52 * mm))

    # -------------------------------------------------------------- results
    story.append(Paragraph("5. Results", s["h1"]))

    group = _best_group(result.scores)
    score_columns = result.score_columns()
    if score_columns:
        fig = charts.indicator_scores(
            result.scores, score_columns, group,
            charts.ChartContext(
                "Indicator scores",
                _scope_line(result, group),
                "Bars are means over the samples in each group. Colour marks the "
                "component: physical, chemical, biological."))
        story.append(_figure(fig, doc, height=104 * mm))

    if result.component_columns() and group:
        fig = charts.component_scores(
            result.scores, group,
            charts.ChartContext("Component scores", _scope_line(result, group),
                                "Error bars show the standard deviation within "
                                "each group; they describe spread, not significance."))
        story.append(_figure(fig, doc, height=84 * mm))

    if group and result.index_column in result.scores.columns:
        fig = charts.index_comparison(
            result.scores, result.index_column, group, result.index_label,
            result.complete_index,
            charts.ChartContext(result.index_label, _scope_line(result, group),
                                "Open circles are individual samples."))
        story.append(_figure(fig, doc, height=84 * mm))

    # ---------------------------------------------------------- aggregated
    wide: list = []
    if not result.aggregated.empty:
        wide.append(Paragraph("6. Aggregated results", s["h1"]))
        wide.append(Paragraph(
            "Means by land use, management, crop and depth. These are "
            "descriptive statistics. No significance test has been carried out, "
            "so a difference between two groups here describes these samples and "
            "is not by itself evidence that the treatments differ.", s["body"]))
        wide.extend(_aggregate_table(result, s))

    if options.include_individual_results and options.detail in ("standard", "full"):
        wide.append(Paragraph("7. Individual results", s["h1"]))
        wide.extend(_individual_table(result, s, options.max_individual_rows))

    if wide:
        story.append(NextPageTemplate("landscape"))
        story.append(PageBreak())
        story.extend(wide)
        story.append(NextPageTemplate("portrait"))
        story.append(PageBreak())

    # ------------------------------------------------------------ warnings
    story.append(Paragraph("8. Points to review", s["h1"]))
    if result.warnings:
        for message in result.warnings:
            story.append(_callout(message, s, WARN_BG))
    else:
        story.append(Paragraph("No warnings were raised.", s["body"]))

    # ---------------------------------------------------------- provenance
    story.append(Paragraph("9. How to reproduce this analysis", s["h1"]))
    story.append(Paragraph(
        "The values below identify the exact calculation path. Given the same "
        "input data, the same software and model versions and the same factor "
        "classes, eSMAF returns the same scores.", s["body"]))
    story.append(_kv_table([
        ("Analysis date", p.get("analysis_datetime", "")),
        ("Software version", p.get("software_version", "")),
        ("Calculation model", f"{p.get('model_id')} — {p.get('model_label')}"),
        ("Model based on", p.get("model_based_on", "")),
        ("Crop database", p.get("crop_db_version", "")),
        ("Project format", str(p.get("project_format_version", ""))),
    ], s))

    if options.detail == "full":
        story.append(PageBreak())
        story.append(Paragraph("Appendix A. Equation parameters", s["h1"]))
        story.append(Paragraph(
            "The coefficients each scoring equation was evaluated with, after "
            "the factor classes and the crop were applied. With more than one "
            "site the same crop appears once per site, because the site's "
            "classes change the coefficients.", s["body"]))
        several = result.several_sites
        for (site, crop), resolved in sorted(result.parameters.items()):
            story.append(Paragraph(f"{site} — {crop}" if several else crop, s["h2"]))
            rows = [["Indicator", "Parameters"]]
            for indicator, values in resolved.values.items():
                if not isinstance(values, dict):
                    continue
                text = ", ".join(
                    f"{k} = {v:.6g}" if isinstance(v, (int, float)) else f"{k} = {v}"
                    for k, v in values.items() if not isinstance(v, dict))
                rows.append([indicator, text])
            story.append(_grid(rows, s, [30 * mm, 144 * mm]))

    doc.build(story)
    return path


# ------------------------------------------------------------------ helpers


def _factor_class_label(factor, code) -> str:
    if code is None:
        return "not selected"
    try:
        return f"{code} — {factor.option(int(code)).label}"
    except (KeyError, ValueError):
        return str(code)


def _factor_section(result: AnalysisResult, s) -> list:
    """The record of how each place was described.

    One site keeps the three-column table earlier reports used. Several sites
    become one column per site, so the reader can see at a glance where two
    places were described differently -- which is the only reason their
    samples were scored against different curves. If the sites do not fit
    across the page, the table continues below with the factor names repeated
    rather than being squeezed.
    """
    used = tuple(result.provenance.get("indicators_used", ()))
    names = [site.name for site in result.sites.sites]
    flowables: list = []

    if len(names) <= 1:
        # Every class is listed, including those no indicator in this dataset
        # happens to use: the table is a record of how the site was described,
        # and a class left out of the record cannot be checked later.
        rows = [["Factor", "Class selected", "Indicators affected"]]
        for factor in fx.FACTORS:
            code = result.factors.as_dict().get(factor.key)
            affected = [BY_KEY[k].label for k in factor.affects if k in used]
            rows.append([factor.label, _factor_class_label(factor, code),
                         ", ".join(affected) or "none in this dataset"])
        if result.sites.from_column:
            flowables.append(Paragraph(
                f"All samples come from one site: <b>{names[0]}</b>.", s["body"]))
        flowables.append(_grid(rows, s, [38 * mm, 62 * mm, 74 * mm]))
        flowables.extend(_spelling_notes(result, s))
        return flowables

    shared = len({tuple(sorted(result.factors_for(n).as_dict().items()))
                  for n in names}) == 1
    counts = {name: int((result.scores["site"] == name).sum())
              for name in names} if "site" in result.scores.columns else {}
    flowables.append(Paragraph(
        f"<b>{len(names)} sites</b> in this dataset"
        + (", all described the same way. Each site was still scored with its "
           "own description; they simply agree."
           if shared else
           ", described separately. Each site's samples were scored against "
           "the curves its own classes produce, which is what makes the scores "
           "comparable across places."), s["body"]))

    rows = [["Factor"] + [f"{n} ({counts.get(n, 0)})" if counts else n
                          for n in names]]
    for factor in fx.FACTORS:
        rows.append([factor.label] + [
            _factor_class_label(factor, result.factors_for(n).as_dict().get(factor.key))
            for n in names])
    # One column per site is the readable shape, but it grows with the number
    # of sites. Rather than splitting a five-site table into three pieces, the
    # table turns the page: landscape first, and only then split.
    width = sum(_natural_widths(rows))
    if width > PORTRAIT_WIDTH:
        flowables.append(NextPageTemplate("landscape"))
        flowables.append(PageBreak())
        flowables.append(Paragraph("2. Site characterisation, continued", s["h2"]))
        flowables.extend(_fitting_tables(rows, s, 1, LANDSCAPE_WIDTH))
    else:
        flowables.extend(_fitting_tables(rows, s, 1, PORTRAIT_WIDTH))
    flowables.append(Paragraph(
        "The number after each site is how many samples came from it. "
        "Every factor class is listed, including those no indicator in this "
        "dataset uses: the table is the record of how each place was "
        "described.", s["small"]))
    flowables.extend(_spelling_notes(result, s))
    if width > PORTRAIT_WIDTH:
        flowables.append(NextPageTemplate("portrait"))
        flowables.append(PageBreak())
    return flowables


def _units_section(result: AnalysisResult, s) -> list:
    """What unit every measurement arrived in, and what was done to it.

    A score can only be read against the basis its curve is defined on, so the
    basis belongs in the record next to the classes and the weights. Where a
    value was converted, the arithmetic is stated in full: a reader who
    disagrees with a conversion can undo it.
    """
    from esmaf_core import units as un

    p = result.provenance
    declared = p.get("units_declared", {})
    conversions = p.get("unit_conversions", [])
    flowables: list = []

    if not declared:
        flowables.append(Paragraph(
            "Every column was taken in the unit the eSMAF template asks for.",
            s["body"]))
        return flowables

    rows = [["Indicator", "Supplied as", "Scored as", "Converted"]]
    for key in p.get("indicators_used", ()):
        if key not in declared:
            continue
        unit_id = declared[key]
        native = un.DEFAULT_UNIT.get(key, "")
        rows.append([BY_KEY[key].label, un.label(key, unit_id),
                     un.label(key, native),
                     "no" if unit_id == native else "yes"])
    if len(rows) > 1:
        flowables.append(_grid(rows, s, [46 * mm, 52 * mm, 46 * mm, 30 * mm]))

    if conversions:
        flowables.append(Spacer(1, 6))
        flowables.append(Paragraph("What each conversion did", s["h2"]))
        for record in conversions:
            flowables.append(Paragraph(
                f"<b>{BY_KEY[record['indicator']].label}</b> "
                f"({record['rows']} values). {record['detail']}", s["body"]))
        rule = p.get("sieved_density_rule", "")
        if any(un.get(r["indicator"], r["from"]) is not None
               and un.get(r["indicator"], r["from"]).volume_basis
               for r in conversions):
            flowables.append(Paragraph(
                "The density used to convert a per-volume result is that of "
                "the air-dried sample sieved to 2 mm, as scooped in the "
                "laboratory, and not the bulk density of the field soil. "
                f"Rule applied: {un.DENSITY_RULES.get(rule, (rule, ''))[0]}.",
                s["small"]))
    return flowables


def _spelling_notes(result: AnalysisResult, s) -> list:
    notes = result.sites.spelling_notes()
    if not notes:
        return []
    return [Spacer(1, 4),
            Paragraph("Site names read as one: " + " ".join(notes), s["small"])]


def _document(path: Path, options: ReportOptions) -> BaseDocTemplate:
    """Portrait for the narrative, landscape for the result tables."""
    doc = BaseDocTemplate(
        str(path), pagesize=PORTRAIT,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=TOP_MARGIN, bottomMargin=BOTTOM_MARGIN,
        title=f"eSMAF report - {options.project_name or 'analysis'}",
        author=options.author or "eSMAF",
    )
    templates = []
    for name, size in (("portrait", PORTRAIT), ("landscape", LANDSCAPE)):
        frame = Frame(MARGIN, BOTTOM_MARGIN,
                      size[0] - 2 * MARGIN, size[1] - TOP_MARGIN - BOTTOM_MARGIN,
                      id=name, leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0)
        templates.append(PageTemplate(id=name, frames=[frame], pagesize=size,
                                      onPage=_furniture))
    doc.addPageTemplates(templates)
    # ``doc.width`` drives the figure sizing and must stay portrait.
    doc.width = PORTRAIT_WIDTH
    return doc


def _scope_line(result: AnalysisResult, group: str | None) -> str:
    frame = result.scores
    parts = []
    for column in ("land_use", "management", "crop", "depth"):
        if column in frame.columns:
            values = sorted({str(v) for v in frame[column]})
            if len(values) == 1:
                parts.append(f"{column.replace('_', ' ')}: {values[0]}")
            else:
                parts.append(f"{column.replace('_', ' ')}: {len(values)} levels")
    scope = "; ".join(parts)
    if group:
        scope += f"  |  grouped by {group.replace('_', ' ')}"
    return scope


def _best_group(frame: pd.DataFrame) -> str | None:
    """Group by the first dimension that actually varies."""
    for column in ("management", "land_use", "crop", "depth"):
        if column in frame.columns and 1 < frame[column].nunique() <= 8:
            return column
    for column in ("land_use", "management", "crop", "depth"):
        if column in frame.columns:
            return column
    return None


def _figure(fig, doc, height) -> Image:
    buffer = io.BytesIO()
    charts.save(fig, buffer, dpi=200)
    buffer.seek(0)
    image = Image(buffer)
    ratio = image.imageHeight / image.imageWidth
    width = doc.width
    if width * ratio > height:
        width = height / ratio
    image.drawWidth = width
    image.drawHeight = width * ratio
    image.hAlign = "CENTER"
    return KeepTogether([image, Spacer(1, 8)])


def _callout(text: str, s, background) -> Table:
    table = Table([[Paragraph(text, s["body"])]], colWidths=[PORTRAIT_WIDTH])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBEFORE", (0, 0), (0, -1), 2.4, ACCENT),
    ]))
    return KeepTogether([table, Spacer(1, 6)])


def _kv_table(rows, s) -> Table:
    data = [[Paragraph(f"<b>{k}</b>", s["cell"]), Paragraph(str(v), s["cell"])]
            for k, v in rows]
    table = Table(data, colWidths=[45 * mm, 129 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def _grid(rows, s, widths) -> Table:
    data = [[Paragraph(f"<b>{c}</b>", s["cellhead"]) for c in rows[0]]]
    data += [[Paragraph(str(c), s["cell"]) for c in row] for row in rows[1:]]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.3, RULE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f6f4")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        # Stated rather than inherited: the width calculation in
        # ``_natural_widths`` has to know how much of each column the padding
        # takes, and ReportLab's default is 6 pt a side.
        ("LEFTPADDING", (0, 0), (-1, -1), CELL_SIDE_PADDING),
        ("RIGHTPADDING", (0, 0), (-1, -1), CELL_SIDE_PADDING),
    ]))
    return table


def _natural_widths(rows: list[list[str]]) -> list[float]:
    """The width each column needs for its own text on one line."""
    widths = []
    for column in range(len(rows[0])):
        header = stringWidth(str(rows[0][column]), CELL_FONT_BOLD, CELL_SIZE)
        body = max((stringWidth(str(row[column]), CELL_FONT, CELL_SIZE)
                    for row in rows[1:]), default=0.0)
        widths.append(max(header, body) + CELL_PADDING)
    return widths


def _drop_constant_keys(rows: list[list[str]], key_count: int) -> tuple[
        list[list[str]], int, list[str]]:
    """Move columns that never vary out of the table and into a caption.

    Repeating "Cropland" down a hundred rows costs a column that the score
    columns then have to do without, and tells the reader nothing they cannot
    read once above the table.
    """
    keep, moved = [], []
    for column in range(key_count):
        values = {str(row[column]) for row in rows[1:]}
        if len(values) == 1 and len(rows) > 2:
            moved.append(f"{rows[0][column]}: {values.pop()}")
        else:
            keep.append(column)
    if not moved:
        return rows, key_count, []
    order = keep + list(range(key_count, len(rows[0])))
    return [[row[c] for c in order] for row in rows], len(keep), moved


def _fitting_tables(rows: list[list[str]], s, key_count: int,
                    available: float) -> list[Table]:
    """Lay the table out at its natural width, splitting it if it will not fit.

    Splitting repeats the identifying columns in each part, so a row can still
    be read across; squeezing every column to a common fraction of the page,
    which is what the first version did, cannot.
    """
    widths = _natural_widths(rows)
    keys = [min(width, MAX_KEY_WIDTH) for width in widths[:key_count]]
    values = widths[key_count:]

    # Keys must leave room for at least a few value columns.
    ceiling = available * 0.55
    if keys and sum(keys) > ceiling:
        scale = ceiling / sum(keys)
        keys = [max(14 * mm, width * scale) for width in keys]
    room = available - sum(keys)

    chunks: list[list[int]] = []
    current: list[int] = []
    used = 0.0
    for index, width in enumerate(values):
        if current and used + width > room:
            chunks.append(current)
            current, used = [], 0.0
        current.append(index)
        used += width
    if current:
        chunks.append(current)

    tables: list[Table] = []
    for number, chunk in enumerate(chunks, start=1):
        data = [[row[c] for c in range(key_count)]
                + [row[key_count + i] for i in chunk] for row in rows]
        chunk_widths = [values[i] for i in chunk]
        column_widths = list(keys) + chunk_widths
        spare = available - sum(column_widths)
        if spare > 0:
            # Whatever the cap took from the identifying columns is given back
            # first -- a wrapped sample code is harder to read than a wrapped
            # score is -- and only then is the rest spread evenly.
            for index, natural in enumerate(widths[:key_count]):
                wanted = min(natural - column_widths[index], spare)
                if wanted > 0:
                    column_widths[index] += wanted
                    spare -= wanted
            if spare > 0:
                share = spare / len(column_widths)
                column_widths = [w + share for w in column_widths]
        table = _grid(data, s, column_widths)
        if len(chunks) > 1:
            caption = Paragraph(
                f"Part {number} of {len(chunks)}. The identifying columns are "
                "repeated in each part." if number == 1 else
                f"Part {number} of {len(chunks)}, continued.", s["small"])
            tables.extend([caption, Spacer(1, 2), table, Spacer(1, 10)])
        else:
            tables.extend([table, Spacer(1, 6)])
    return tables


def _aggregate_table(result: AnalysisResult, s) -> list:
    frame = result.aggregated
    # "sites" names the places pooled into each row. It is not a grouping key --
    # the comparison here is between land uses and managements -- but a mean
    # over two farms has to say so.
    keys = [c for c in ("land_use", "management", "crop", "depth", "sites")
            if c in frame.columns]
    metrics = [f"{c}_mean" for c in
               [f"{comp}_component" for comp in COMPONENTS] + [result.index_column]
               if f"{c}_mean" in frame.columns]
    count = next((c for c in frame.columns if c.endswith("_count")), None)

    header = [k.replace("_", " ").title() for k in keys]
    header += [COMPONENT_LABELS.get(m.replace("_component_mean", ""), m)
               for m in metrics[:-1]]
    header += [_index_abbreviation(result)]
    if count:
        header.append("n")

    rows = [header]
    for _, record in frame.iterrows():
        row = [str(record[k]) for k in keys]
        row += [f"{record[m]:.2f}" if pd.notna(record[m]) else "—" for m in metrics]
        if count:
            row.append(str(int(record[count])) if pd.notna(record[count]) else "—")
        rows.append(row)

    flowables = _fitting_tables(rows, s, len(keys), LANDSCAPE_WIDTH)
    flowables.append(Paragraph(
        f"{_index_abbreviation(result)} = {result.index_label}. "
        "n is the number of samples in the group.", s["small"]))
    return flowables


def _individual_table(result: AnalysisResult, s, limit: int) -> list:
    frame = result.scores
    # Site first: with more than one place in the file, "sample 6" alone does
    # not identify a row. With one place it is constant and drops out below.
    keys = [c for c in ("site", "land_use", "management", "crop", "depth",
                        "sample") if c in frame.columns]
    columns = result.score_columns() + result.component_columns() + [result.index_column]
    columns = [c for c in columns if c in frame.columns]
    shown = frame.head(limit)

    header = [k.replace("_", " ").title() for k in keys] + \
             [_short(c, result) for c in columns]
    rows = [header]
    for _, record in shown.iterrows():
        row = [str(record[k]) for k in keys]
        row += [f"{record[c]:.2f}" if pd.notna(record[c]) else "—" for c in columns]
        rows.append(row)

    rows, key_count, moved = _drop_constant_keys(rows, len(keys))
    flowables: list = []
    if moved:
        flowables.append(Paragraph(
            "The same for every sample below — " + "; ".join(moved) + ".",
            s["small"]))
        flowables.append(Spacer(1, 4))
    flowables.extend(_fitting_tables(rows, s, key_count, LANDSCAPE_WIDTH))
    flowables.append(Paragraph(_legend(columns, result), s["small"]))
    if len(frame) > limit:
        flowables.append(Spacer(1, 3))
        flowables.append(Paragraph(
            f"Showing the first {limit} of {len(frame)} samples. "
            "The Excel export contains every row.", s["small"]))
    return flowables


def _index_abbreviation(result: AnalysisResult) -> str:
    return "".join(word[0] for word in result.index_label.split()
                   if word[0].isupper()) or "Index"


def _short(column: str, result: AnalysisResult) -> str:
    if column.endswith("_score"):
        key = column[:-6]
        return {"WFPS_BiolAct": "WFPS-b", "WFPS_EnvProtect": "WFPS-e"}.get(key, key)
    if column.endswith("_component"):
        return column[:-10][:4].capitalize()
    return _index_abbreviation(result)


def _legend(columns: list[str], result: AnalysisResult) -> str:
    """Spell out the abbreviated headings, so the table can stay narrow."""
    parts = []
    for column in columns:
        short = _short(column, result)
        if column.endswith("_score"):
            key = column[:-6]
            if key in ("WFPS_BiolAct", "WFPS_EnvProtect"):
                full = ("water-filled pore space, biological activity"
                        if key.endswith("BiolAct") else
                        "water-filled pore space, environmental protection")
            else:
                full = BY_KEY[key].label.lower() if key in BY_KEY else key
        elif column.endswith("_component"):
            full = COMPONENT_LABELS.get(column[:-10], column).lower() + " component"
        else:
            full = result.index_label
        parts.append(f"{short} = {full}")
    return "All values are scores from 0 to 1. " + "; ".join(parts) + "."


def _furniture(canvas, doc) -> None:
    width = canvas._pagesize[0]      # portrait and landscape pages both arrive here
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN, 14 * mm, width - MARGIN, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(SOFT)
    canvas.drawString(MARGIN, 9 * mm,
                      "Generated with eSMAF — Electronic Soil Management Assessment Framework")
    canvas.drawRightString(width - MARGIN, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()
