"""The analysis check that runs before any score is computed.

An *error* means the analysis cannot be produced safely and is blocked.
A *warning* means it can run but something deserves a second look.  Keeping
the two apart is what stops the application from being either dangerous or
insufferable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from . import factors as fx
from .crops import find_crop, suggest_crops
from .indicators import BY_KEY, COMPONENTS, INDICATORS, indicators_for
from .models import load_model
from . import version as ver
from .weights import WeightConfig

Severity = Literal["error", "warning", "info"]


@dataclass
class Finding:
    severity: Severity
    where: str            # column, row range, or setting the problem concerns
    what: str             # what is wrong
    why: str = ""         # why it matters
    fix: str = ""         # what the user can do
    rows: list[int] = field(default_factory=list)
    scope: str = ""       # "analysis" or the indicator key affected

    def one_line(self) -> str:
        return f"[{self.severity.upper()}] {self.where}: {self.what}"


@dataclass
class CheckReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "info"]

    @property
    def can_run(self) -> bool:
        return not self.errors

    def add(self, severity: Severity, where: str, what: str, why: str = "",
            fix: str = "", rows: list[int] | None = None, scope: str = "") -> None:
        self.findings.append(Finding(severity, where, what, why, fix,
                                     rows or [], scope))

    def summary(self) -> str:
        if self.errors:
            return (f"{len(self.errors)} problem"
                    f"{'' if len(self.errors) == 1 else 's'} must be resolved "
                    f"before the analysis can run")
        if self.warnings:
            return (f"Ready to calculate, with {len(self.warnings)} point"
                    f"{'' if len(self.warnings) == 1 else 's'} to review")
        return "Ready to calculate"


def check(frame: pd.DataFrame, factors: fx_selection, weight_config: WeightConfig,
          model_id: str, site_factors: dict | None = None,
          site_index=None, units: dict | None = None,
          question_open: bool = False) -> CheckReport:
    """Run every pre-flight check over data, factor classes and weights.

    ``site_factors`` maps site name to its own selection. When it is given,
    the factor classes are checked once per site and every message says which
    site it is about; when it is not, ``factors`` describes the whole dataset.

    ``units`` maps indicator key to the unit the user declared for it.
    """
    report = CheckReport()
    _check_data(frame, report, units, model_id)
    _check_units(frame, units, model_id, report)
    _check_sites(frame, site_index, report, question_open)
    _check_crops(frame, report)
    if site_factors:
        for name in sorted(site_factors):
            _check_factors(frame, site_factors[name], weight_config, model_id,
                           report, site=name)
    else:
        _check_factors(frame, factors, weight_config, model_id, report)
    _check_weights(frame, weight_config, report)
    _check_coverage(frame, weight_config, report)
    return report


def _check_units(frame: pd.DataFrame, declared: dict | None, model_id: str,
                 report: CheckReport) -> None:
    """Every indicator column has to say what unit it is in.

    This is the one property of the data that cannot be inferred from the
    data. Organic carbon of 3.7 % and organic matter of 3.7 g dm-3 are the
    same number, describe soils an order of magnitude apart, and no range
    check can tell them apart -- only the person who produced the value can.
    So the declaration is required, and the plausibility net below catches
    only the subset of mistakes that happen to be arithmetically visible.
    """
    from . import units as un

    declared = declared or {}
    model = load_model(model_id)
    present = [ind.key for ind in INDICATORS if ind.key in frame.columns]

    for key in present:
        indicator = BY_KEY[key]
        choices = un.options(key)
        if not un.must_be_declared(key):
            continue
        unit_id = declared.get(key)
        if not unit_id:
            report.add(
                "error", f"{indicator.label} — unit",
                "The unit of this column has not been stated.",
                why=("The scoring curve is defined on one basis only, and the "
                     "numbers alone cannot say which basis they are on."),
                fix=("State it on the Data page. Expected by the template: "
                     f"{un.label(key, un.DEFAULT_UNIT[key])}."),
                scope=key,
            )
            continue
        if un.get(key, unit_id) is None:
            report.add(
                "error", f"{indicator.label} — unit",
                f"'{unit_id}' is not a unit eSMAF knows for this indicator.",
                fix="Choose one of: " + ", ".join(u.label for u in choices),
                scope=key,
            )
            continue
        message = un.review(key, frame[key], unit_id, model)
        if message:
            report.add(
                "warning", f"{indicator.label} — unit",
                message,
                why=("A column declared in the wrong unit is the one mistake "
                     "that changes every score derived from it without "
                     "looking like an error."),
                fix="Confirm the unit on the Data page, or correct the values.",
                scope=key,
            )
        unit = un.get(key, unit_id)
        if unit is None:
            continue
        if unit.bulk_basis and "BD" not in frame.columns:
            report.add(
                "error", f"{indicator.label} — unit",
                f"Supplied as {unit.label}, which cannot be converted without "
                "a bulk density column.",
                why=("Water content per volume refers to the volume of intact "
                     "soil, so the divisor is the field bulk density of the "
                     "same sample — the one property this file does not carry."),
                fix=("Add a bulk density column, or supply the values on a "
                     "gravimetric basis."),
                scope=key,
            )
        if not unit.native:
            report.add(
                "info", f"{indicator.label} — unit",
                f"Supplied as {unit.label}; {unit.note[0].lower()}{unit.note[1:]}",
                why="The conversion is recorded with the result.",
            )


def _check_sites(frame: pd.DataFrame, site_index, report: CheckReport,
                 question_open: bool = False) -> None:
    """The site column decides which curves each row is scored against."""
    if "site" not in frame.columns:
        return

    if question_open:
        report.add(
            "error", "Sites",
            "It has not been said whether these sites share a soil.",
            why=("Factor classes are what tune every curve to a soil. Applying "
                 "one description to several places, or asking for a separate "
                 "one, is a decision about the places themselves."),
            fix=("On the Setup page, say whether all sites share the same "
                 "factor classes or are described separately."),
        )

    blank = [i for i, value in zip(frame.index, frame["site"])
             if value is None or str(value).strip() == ""
             or str(value).strip().lower() == "nan"]
    if blank and len(blank) < len(frame):
        report.add(
            "error", "Site",
            f"{len(blank)} row(s) have no site while the others do.",
            why=("Each site is described separately, so a row without one "
                 "cannot be matched to a set of factor classes."),
            fix=("Fill the site column for these rows, or clear it entirely if "
                 "every sample comes from the same place."),
            rows=blank[:50], scope="site",
        )

    if site_index is None:
        return
    for note in site_index.spelling_notes():
        report.add("info", "Site", note,
                   why="Case, accents and punctuation are set aside when site "
                       "names are compared.",
                   fix="If these are different places, give them clearly "
                       "different names in the spreadsheet.")
    for suggestion in site_index.suggestions:
        report.add(
            "warning", "Site",
            f"'{suggestion.first}' and '{suggestion.second}' are spelled "
            "almost the same.",
            why=("They are being treated as two places, each with its own "
                 "factor classes, because only you can say whether they are "
                 "one."),
            fix=("On the Setup page you can join them into one site, or leave "
                 "them separate and describe each."),
        )


# ``factors`` is a plain dict of factor key -> class code, so that the check can
# run before a SiteFactors object exists.
fx_selection = dict


def _numeric_indicator_columns(frame: pd.DataFrame) -> list[str]:
    return [ind.key for ind in INDICATORS if ind.key in frame.columns]


def _check_data(frame: pd.DataFrame, report: CheckReport,
                declared: dict | None = None,
                model_id: str = ver.DEFAULT_MODEL_ID) -> None:
    """Numbers that cannot be scored, and numbers that deserve a second look.

    The ranges belong to the scoring curve, so the values are put on the
    curve's basis first: a column declared in another unit is checked as the
    engine will read it, not as it happens to be written in the file.
    """
    if frame.empty:
        report.add("error", "Dataset", "The dataset has no rows.",
                   fix="Import a spreadsheet or add rows by hand.")
        return

    for column in ("land_use", "management", "crop", "depth"):
        if column not in frame.columns:
            report.add(
                "warning", column.replace("_", " ").title(),
                "This grouping column is missing.",
                why=("Results can still be computed, but samples cannot be "
                     "compared across this dimension."),
                fix="Map a column to it on the Data page, or add it to the file.",
            )
        elif frame[column].isna().any():
            rows = frame.index[frame[column].isna()].tolist()
            report.add(
                "warning", column.replace("_", " ").title(),
                f"{len(rows)} row(s) have no value.",
                why="These rows will be grouped under '(not given)'.",
                fix="Fill the missing values so the groups are meaningful.",
                rows=rows[:50],
            )

    from . import units as un

    model = load_model(model_id)
    declared = declared or {}

    for key in _numeric_indicator_columns(frame):
        indicator = BY_KEY[key]
        supplied = pd.to_numeric(frame[key], errors="coerce")
        series, basis = un.on_curve_basis(key, supplied, declared.get(key), model)
        original = frame[key]

        non_numeric = original.notna() & series.isna()
        if non_numeric.any():
            rows = frame.index[non_numeric].tolist()
            examples = ", ".join(str(v) for v in original[non_numeric].head(3))
            report.add(
                "error", indicator.canonical_column,
                f"{int(non_numeric.sum())} value(s) are not numeric (e.g. {examples}).",
                why="A non-numeric value cannot be scored and would be read as missing.",
                fix=("Replace text such as '<0.01', 'nd' or 'n.a.' with a number, "
                     "or leave the cell empty to mark the measurement as absent."),
                rows=rows[:50], scope=key,
            )

        lo, hi = indicator.hard_limits
        impossible = series.notna() & ((series < lo) | (series > hi))
        if impossible.any():
            rows = frame.index[impossible].tolist()
            report.add(
                "error", indicator.canonical_column,
                f"{int(impossible.sum())} value(s) fall outside the possible range "
                f"{lo:g} to {hi:g} {indicator.unit}{basis}.",
                why="Values like these usually mean a unit or a column mix-up.",
                fix=(f"Check the unit declared for {indicator.label} on the Data "
                     f"page, and that the column holds what it says."),
                rows=rows[:50], scope=key,
            )

        lo, hi = indicator.plausible
        unusual = series.notna() & ((series < lo) | (series > hi)) & ~impossible
        if unusual.any():
            rows = frame.index[unusual].tolist()
            report.add(
                "warning", indicator.canonical_column,
                f"{int(unusual.sum())} value(s) lie outside the usual range "
                f"{lo:g} to {hi:g} {indicator.unit}.",
                why="Unusual is not impossible, but it is worth confirming.",
                fix=f"Confirm the unit is {indicator.unit} and the values are correct.",
                rows=rows[:50], scope=key,
            )

        if key == "WFPS":
            looks_percent = series.notna() & (series > 1.0)
            if looks_percent.any():
                report.add(
                    "error", indicator.canonical_column,
                    f"{int(looks_percent.sum())} value(s) are above 1.",
                    why=("Water-filled pore space enters the equation as a fraction. "
                         "A value of 60 instead of 0.60 scores zero and silently "
                         "drags down the physical component."),
                    fix="Divide by 100, or set the column conversion on the Data page.",
                    rows=frame.index[looks_percent].tolist()[:50], scope=key,
                )

    if "SAR" in frame.columns and "EC" not in frame.columns:
        report.add(
            "warning", "SAR",
            "Sodium adsorption ratio is present but electrical conductivity is not.",
            why="The SAR curve branches on EC, so SAR cannot be scored without it.",
            fix="Add an EC column, or remove SAR from the analysis.",
            scope="SAR",
        )

    # Site belongs in this key. Two farms sampled under the same management and
    # depth will both number their replicates from one, and calling twenty
    # perfectly ordinary rows duplicates would teach the user to ignore the
    # check.
    needed = ("land_use", "management", "crop", "depth", "sample")
    duplicate_keys = [c for c in ("site",) + needed if c in frame.columns]
    if all(c in frame.columns for c in needed):
        duplicated = frame.duplicated(subset=duplicate_keys, keep=False)
        if duplicated.any():
            named = ", ".join(k.replace("_", " ") for k in duplicate_keys[:-1])
            report.add(
                "warning", "Sample identification",
                f"{int(duplicated.sum())} rows share the same {named} and "
                "sample number.",
                why="Repeated identifiers usually mean a duplicated row or a "
                    "sample number that was not incremented.",
                fix="Give each replicate its own sample number.",
                rows=frame.index[duplicated].tolist()[:50],
            )


def _check_crops(frame: pd.DataFrame, report: CheckReport) -> None:
    if "crop" not in frame.columns:
        report.add("error", "Crop",
                   "No crop column was found.",
                   why="pH, EC and P are scored against crop-specific optima.",
                   fix="Map a column to Crop on the Data page.")
        return
    for name in sorted({str(v) for v in frame["crop"].dropna().unique()}):
        if find_crop(name) is None:
            suggestions = suggest_crops(name)
            hint = (" Closest entries: " + ", ".join(suggestions) + "."
                    if suggestions else "")
            rows = frame.index[frame["crop"].astype(str) == name].tolist()
            report.add(
                "error", "Crop",
                f"'{name}' is not in the crop database.",
                why="Without crop parameters the pH, EC and P curves cannot be built.",
                fix=("Pick an existing crop for these rows, or request the addition "
                     "of this crop to the database." + hint),
                rows=rows[:50],
            )


def _check_factors(frame: pd.DataFrame, selection: dict, weight_config: WeightConfig,
                   model_id: str, report: CheckReport, site: str = "") -> None:
    model = load_model(model_id)
    where = (lambda label: f"{site} — {label}") if site else (lambda label: label)
    available = {ind.key for ind in INDICATORS if ind.key in frame.columns}
    available -= weight_config.excluded

    # Every factor class must be chosen, including those no indicator in this
    # particular dataset happens to use. Leaving one blank because "it does not
    # matter here" is how a site ends up characterised differently between two
    # analyses of the same field.
    for factor in fx.FACTORS:
        code = selection.get(factor.key)
        if code is None:
            used = [BY_KEY[k].label for k in factor.affects if k in available]
            report.add(
                "error", where(factor.label),
                "No class selected.",
                why=factor.why,
                fix=("Choose a class on the Setup page."
                     + (f" Affects: {', '.join(used)}." if used else
                        " No indicator in this dataset uses it, but it is part of"
                        " the site description and is recorded with the result.")),
            )
        elif code not in factor.codes:
            report.add(
                "error", where(factor.label),
                f"Class {code} is not one of the defined classes.",
                fix=f"Valid classes: {', '.join(str(c) for c in factor.codes)}.",
            )

    texture = selection.get("texture")
    if texture and texture > model.texture_classes:
        report.add(
            "error", where("Texture"),
            f"Class {texture} is not available in model '{model.id}'.",
            why=f"This model defines {model.texture_classes} texture classes.",
            fix="Choose a lower class or switch to a model with five texture classes.",
        )

    _check_unusual(selection, report, where)


def _check_unusual(selection: dict, report: CheckReport, where=None) -> None:
    where = where or (lambda label: label)
    weathering = selection.get("weathering")
    p_method = selection.get("p_method")
    texture = selection.get("texture")
    mineral = selection.get("mineral")
    organic = selection.get("organic_matter")
    climate = selection.get("climate")
    region = selection.get("region")

    if weathering == 1 and p_method == 5:
        report.add(
            "warning", where("P method / Weathering"),
            "Resin-extracted phosphorus combined with a carbonate soil.",
            why="This pairing is unusual and carries a method factor of 2.1.",
            fix="Confirm both the extraction method and the weathering class.",
        )
    if texture and texture >= 4 and mineral is None:
        report.add(
            "warning", where("Clay mineralogy"),
            "Not selected, although the texture is fine.",
            why="From texture class 4 upwards, mineralogy shifts the bulk density curve.",
            fix="Select a mineralogy class, or accept the 'other clays' default.",
        )
    if organic == 1 and climate in (2, 4):
        report.add(
            "warning", where("Organic matter / Climate"),
            "A very high inherent organic matter class in a low-rainfall climate.",
            why=("The organic matter class describes the soil type, not the "
                 "carbon you measured. This combination is rare."),
            fix="Re-read the class from the soil classification of the site.",
        )
    if region == 1 and climate == 1:
        report.add(
            "warning", where("Region / Climate"),
            "Arid region combined with the high-rainfall climate class.",
            why="These two selections contradict each other.",
            fix="Review both; they are read from different sources but must agree.",
        )


def _check_weights(frame: pd.DataFrame, weight_config: WeightConfig,
                   report: CheckReport) -> None:
    from .indicators import INDICATORS

    available = {i.key for i in INDICATORS if i.key in frame.columns}
    for problem in weight_config.validate(available):
        report.add(
            "error", "Weights", problem,
            why="Weights define proportions; a total other than 100 % is ambiguous.",
            fix="Adjust the values, or switch to an equal-weight scheme.",
        )


def _check_coverage(frame: pd.DataFrame, weight_config: WeightConfig,
                    report: CheckReport) -> None:
    available = {ind.key for ind in INDICATORS if ind.key in frame.columns
                 and pd.to_numeric(frame[ind.key], errors="coerce").notna().any()}
    available -= weight_config.excluded

    covered = [c for c in COMPONENTS
               if any(ind.key in available for ind in indicators_for(c))]
    if not covered:
        report.add("error", "Indicators", "No indicator has usable values.",
                   fix="Check the column mapping on the Data page.")
        return

    missing_components = [c for c in COMPONENTS if c not in covered]
    if missing_components:
        report.add(
            "info", "Index",
            f"No {' or '.join(missing_components)} indicator is available.",
            why=("The result will be a partial index rather than the Soil Health "
                 "Index. It is renormalised so it still ranges from 0 to 1, but "
                 "it describes fewer soil functions and is not comparable with a "
                 "complete index."),
            fix="Add at least one indicator from each component for a full index.",
        )

    for component in covered:
        members = indicators_for(component)
        have = [i for i in members if i.key in available]
        if len(have) < len(members):
            absent = [i.label for i in members if i.key not in available]
            report.add(
                "info", f"{component.capitalize()} component",
                f"Computed from {len(have)} of {len(members)} indicators.",
                why=("Weights are renormalised over what is present, so the "
                     "component can still reach 1.00; the missing indicators "
                     "simply do not inform it."),
                fix=f"Not measured: {', '.join(absent)}.",
            )

    for key in sorted(available):
        series = pd.to_numeric(frame[key], errors="coerce")
        missing = int(series.isna().sum())
        if missing:
            report.add(
                "info", BY_KEY[key].canonical_column,
                f"{missing} of {len(series)} rows have no value.",
                why=("Those rows are scored on the indicators they do have; "
                     "no row and no column is discarded."),
                fix="",
                scope=key,
            )
