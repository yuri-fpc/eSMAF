"""The calculation engine.

Input -> validation -> scoring -> components -> index, with a trace for every
number produced.  Nothing in this module imports a user interface, so the
whole scientific path can be exercised from a test, a script or a future
interface without change.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from . import equations as eq
from . import sites as st
from . import units as un
from . import version as ver
from . import weights as wt
from .crops import Crop, UnknownCrop, find_crop
from .indicators import BY_KEY, COMPONENTS, CONTEXT_COLUMNS, INDICATORS, Indicator
from .models import Model, load_model
from .parameters import (ParameterError, ResolvedParameters, SiteFactors,
                         resolve, to_saturation_basis)

GROUPING_COLUMNS = ("land_use", "management", "crop", "depth")

#: What the engine accepts for the site description: one set of factor classes
#: for the whole dataset, or one set per site.
Factors = "SiteFactors | Mapping[str, SiteFactors]"

#: Score columns produced per indicator. WFPS is the only one-to-many case.
SCORE_KEYS: dict[str, tuple[str, ...]] = {
    ind.key: (("WFPS_BiolAct", "WFPS_EnvProtect") if ind.key == "WFPS" else (ind.key,))
    for ind in INDICATORS
}


@dataclass
class AnalysisOptions:
    model_id: str = ver.DEFAULT_MODEL_ID
    round_scores: int = 2
    #: When False, a row missing an indicator is scored on what it has.
    #: When True, rows with any missing indicator are excluded entirely.
    require_complete_rows: bool = False
    #: Indicator key -> unit identifier, as declared by the user. Anything not
    #: named here is taken to be in the unit the eSMAF template asks for,
    #: which is what every earlier version assumed for everything.
    units: dict[str, str] = field(default_factory=dict)
    #: How the density that converts a volume basis to a mass basis is
    #: obtained. See :mod:`esmaf_core.units`.
    density_rule: str = un.DEFAULT_DENSITY_RULE


@dataclass
class AnalysisResult:
    """Everything an analysis produced, including how it produced it."""

    scores: pd.DataFrame                       # one row per sample
    aggregated: pd.DataFrame                   # one row per group
    weights: wt.AppliedWeights
    factors: SiteFactors                       # the first site's, for one-site work
    site_factors: dict[str, SiteFactors]       # what each site was scored with
    parameters: dict[tuple[str, str], ResolvedParameters]   # keyed by (site, crop)
    sites: st.SiteIndex
    conversions: list                          # what each unit declaration did
    supplied: pd.DataFrame                     # values exactly as the user gave them
    index_column: str
    index_label: str
    complete_index: bool
    available_indicators: tuple[str, ...]
    missing_indicators: tuple[str, ...]
    warnings: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    raw: pd.DataFrame | None = None

    @property
    def n_samples(self) -> int:
        return len(self.scores)

    @property
    def several_sites(self) -> bool:
        return len(self.site_factors) > 1

    def factors_for(self, site: str) -> SiteFactors:
        """The description a given site was scored with."""
        return self.site_factors.get(site, self.factors)

    def site_of(self, row: pd.Series) -> str:
        """Which site a scored row belongs to."""
        value = row.get("site")
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return next(iter(self.site_factors), st.SINGLE_SITE)
        return str(value)

    def score_columns(self) -> list[str]:
        return [c for c in self.scores.columns if c.endswith("_score")]

    def component_columns(self) -> list[str]:
        return [f"{c}_component" for c in COMPONENTS
                if f"{c}_component" in self.scores.columns]

    def summary_line(self) -> str:
        kind = "complete" if self.complete_index else "partial"
        return (f"{self.n_samples} samples, {len(self.available_indicators)} indicators, "
                f"{kind} index ({self.index_label})")


def run(data: pd.DataFrame, factors, weight_config: wt.WeightConfig,
        options: AnalysisOptions | None = None,
        site_index: st.SiteIndex | None = None) -> AnalysisResult:
    """Score a prepared dataset.

    ``data`` must carry the grouping columns plus one column per indicator,
    named with the indicator key (``BD``, ``pH``, ...), already in the units
    declared in :mod:`esmaf_core.indicators`.

    ``factors`` is either one :class:`SiteFactors` for the whole dataset or a
    mapping of site name to :class:`SiteFactors`. A dataset with a ``site``
    column and one set of factor classes is the ordinary case of several
    places that happen to share a description; a mapping is what makes each
    place score against its own curves.
    """
    options = options or AnalysisOptions()
    model = load_model(options.model_id)
    frame = data.copy()
    warnings: list[str] = []

    index = site_index or st.build(frame["site"] if "site" in frame.columns else None)
    if "site" in frame.columns:
        frame["site"] = [index.resolve(value) for value in frame["site"]]
    else:
        frame["site"] = index.names[0]
    site_factors = _factors_by_site(factors, index.names)

    # Units first, and before anything is scored. The conversion from a volume
    # to a mass basis needs the texture class of the site the sample came
    # from, which is why it happens here rather than at import: the site
    # description is not known until now.
    supplied = frame.copy()
    frame, conversions, unit_warnings = un.convert(
        frame, options.units, model,
        lambda name: site_factors[name].texture if name in site_factors else None,
        options.density_rule)
    warnings.extend(unit_warnings)

    for column in GROUPING_COLUMNS:
        if column not in frame.columns:
            frame[column] = "(not given)"
        frame[column] = frame[column].fillna("(not given)").astype(str)

    present = [ind.key for ind in INDICATORS if ind.key in frame.columns]
    if not present:
        raise NoIndicatorsError(
            "None of the columns in this dataset was recognised as a soil "
            "health indicator, so there is nothing to score."
        )

    usable: list[str] = []
    for key in present:
        numeric = pd.to_numeric(frame[key], errors="coerce")
        frame[key] = numeric
        if numeric.notna().any():
            usable.append(key)
        else:
            warnings.append(
                f"{BY_KEY[key].label} was present but held no numeric value, "
                "so it was left out of the analysis."
            )

    excluded = weight_config.excluded & set(usable)
    if excluded:
        labels = ", ".join(sorted(BY_KEY[k].label for k in excluded))
        warnings.append(f"Excluded by choice: {labels}.")
    usable = [k for k in usable if k not in weight_config.excluded]
    if not usable:
        raise NoIndicatorsError(
            "Every recognised indicator was either empty or excluded, so no "
            "score can be produced."
        )

    applied = wt.apply(weight_config, set(usable))

    # Resolve parameters once per site and crop rather than once per row. The
    # site is in the key because the factor classes -- and therefore every
    # coefficient below -- may differ from one place to the next.
    parameters: dict[tuple[str, str], ResolvedParameters] = {}
    crops: dict[str, Crop] = {}
    for name in sorted(frame["crop"].unique()):
        crop = find_crop(name)
        if crop is None:
            raise UnknownCrop(name, _suggest(name))
        crops[name] = crop
    for site in sorted(frame["site"].unique()):
        here = site_factors[site]
        for name, crop in crops.items():
            resolved = resolve(model, here, crop)
            parameters[(site, name)] = resolved
            for message in resolved.warnings:
                # Not prefixed with the site: every warning resolve() raises is
                # about the crop database, so the same gap seen at four sites
                # is one problem, not four. A future site-specific warning
                # should name its site in the message itself.
                if message not in warnings:
                    warnings.append(message)
    warnings[:] = _collapse(warnings)

    rows: list[dict[str, Any]] = []
    for position, (_, row) in enumerate(frame.iterrows()):
        key = (row["site"], row["crop"])
        rows.append(_score_row(row, crops[row["crop"]], parameters[key],
                               model, site_factors[row["site"]], applied,
                               usable, options, position))
    scored = pd.DataFrame(rows, index=frame.index)

    context = [c for c in CONTEXT_COLUMNS if c in frame.columns]
    measured = [k for k in usable]
    result_frame = pd.concat(
        [frame[context + measured], scored], axis=1
    )

    components_present = tuple(
        c for c in COMPONENTS if f"{c}_component" in result_frame.columns
        and result_frame[f"{c}_component"].notna().any()
    )
    index_label = wt.index_name(components_present)
    index_column = "soil_health_index" if wt.is_complete(components_present) else "quality_index"

    if not wt.is_complete(components_present):
        missing = [c for c in COMPONENTS if c not in components_present]
        warnings.append(
            f"No {' or '.join(missing)} indicator was available, so the result "
            f"is a partial index ({index_label}) and not the Soil Health Index. "
            "Partial indices are renormalised over the components present, so "
            "they still range from 0 to 1, but they describe fewer soil functions."
        )

    aggregated = aggregate(result_frame, index_column)

    provenance = ver.provenance() | {
        "model_id": model.id,
        "model_label": model.label,
        "model_based_on": model.based_on,
        "analysis_datetime": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "weighting_scheme": weight_config.scheme,
        "weighting_scheme_label": wt.SCHEME_LABELS.get(weight_config.scheme, weight_config.scheme),
        # One site keeps the flat block earlier versions wrote, so an older
        # report and a new one can still be compared line by line.
        "factor_classes": site_factors[index.names[0]].as_dict(),
        "sites": [
            {"name": name,
             "spellings": list(site.spellings),
             "rows": int((frame["site"] == name).sum()),
             "factor_classes": site_factors[name].as_dict()}
            for name, site in ((s.name, s) for s in index.sites)
        ],
        "site_column_used": index.from_column,
        "units_declared": {k: v for k, v in options.units.items() if k in usable},
        "unit_conversions": [
            {"indicator": c.indicator, "from": c.declared, "to": c.to,
             "detail": c.detail, "rows": c.rows} for c in conversions],
        "sieved_density_rule": options.density_rule,
        "indicator_weights": {k: round(v, 6) for k, v in applied.indicator.items()},
        "component_weights": {k: round(v, 6) for k, v in applied.component.items()},
        "indicators_used": tuple(usable),
        "index": index_label,
        "complete_index": wt.is_complete(components_present),
        "n_samples": len(result_frame),
        "crops": sorted(crops),
    }
    if model.deprecated:
        warnings.insert(0, (
            f"Model '{model.id}' is deprecated and reproduces known defects of "
            "the web version. Use it only to regenerate historical results."
        ))

    return AnalysisResult(
        scores=result_frame,
        aggregated=aggregated,
        weights=applied,
        factors=site_factors[index.names[0]],
        site_factors=site_factors,
        parameters=parameters,
        sites=index,
        conversions=conversions,
        supplied=supplied,
        index_column=index_column,
        index_label=index_label,
        complete_index=wt.is_complete(components_present),
        available_indicators=tuple(usable),
        missing_indicators=applied.missing_indicators,
        warnings=warnings,
        provenance=provenance,
        raw=data,
    )


def _score_row(row: pd.Series, crop: Crop, params: ResolvedParameters, model: Model,
               factors: SiteFactors, applied: wt.AppliedWeights, usable: Iterable[str],
               options: AnalysisOptions, position: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    traces = score_row_detail(row, crop, params, model, factors, usable)

    for score_key, result in traces.items():
        out[f"{score_key}_score"] = round(result.value, options.round_scores)

    # Components: renormalise over the indicators this row actually has.
    component_values: dict[str, float] = {}
    for component in COMPONENTS:
        contributions: list[tuple[str, float, float]] = []
        for indicator_key, weight in applied.indicator.items():
            if BY_KEY[indicator_key].component != component:
                continue
            subkeys = SCORE_KEYS[indicator_key]
            share = weight / len(subkeys)
            for subkey in subkeys:
                result = traces.get(subkey)
                if result is not None:
                    contributions.append((subkey, share, result.value))
        if not contributions:
            out[f"{component}_component"] = None
            continue
        total_weight = sum(w for _, w, _ in contributions)
        value = sum(w * v for _, w, v in contributions) / total_weight
        component_values[component] = value
        out[f"{component}_component"] = round(value, options.round_scores)

    if component_values:
        total = sum(applied.component.get(c, 0.0) for c in component_values)
        if total > 0:
            index = sum(applied.component.get(c, 0.0) * v
                        for c, v in component_values.items()) / total
        else:
            index = sum(component_values.values()) / len(component_values)
        column = ("soil_health_index"
                  if wt.is_complete(tuple(component_values)) else "quality_index")
        out[column] = round(index, options.round_scores)
        out["index_components"] = "+".join(sorted(component_values))
    return out


def score_row_detail(row: pd.Series, crop: Crop, params: ResolvedParameters,
                     model: Model, factors: SiteFactors,
                     usable: Iterable[str]) -> dict[str, eq.ScoreResult]:
    """Score one row and keep the full trace for every indicator.

    Called both by the batch path (which keeps only the numbers) and by the
    interface when the user clicks a result to ask how it was produced.
    """
    usable = set(usable)
    traces: dict[str, eq.ScoreResult] = {}

    def value(key: str) -> float | None:
        if key not in usable or key not in row:
            return None
        raw = row[key]
        return None if pd.isna(raw) else float(raw)

    if (x := value("BD")) is not None:
        traces["BD"] = eq.score_bd(x, **params["BD"])

    if (x := value("AGG")) is not None:
        traces["AGG"] = eq.score_agg(x, **params["AGG"])

    if (x := value("WFPS")) is not None:
        if model.switch("wfps_input") == "percent_literal":
            wfps = x
        else:
            wfps = x / 100.0 if x > 1.0 else x
        traces["WFPS_BiolAct"] = eq.score_wfps_biological(wfps, **params["WFPS_BiolAct"])
        traces["WFPS_EnvProtect"] = eq.score_wfps_environmental(
            wfps, **params["WFPS_EnvProtect"])

    if (x := value("AWC")) is not None:
        awc = params["AWC"]
        fn = eq.score_awc_arid if awc["region"] == "arid" else eq.score_awc_humid
        traces["AWC"] = fn(x, awc["a"], awc["b"], awc["c"], awc["d"])

    if (x := value("pH")) is not None and params["pH"]["c"] > 0:
        traces["pH"] = eq.score_ph(x, **params["pH"])

    if (x := value("K")) is not None:
        traces["K"] = eq.score_k(x, **params["K"])

    if (x := value("P")) is not None:
        traces["P"] = eq.score_p(x, **params["P"])

    ec = value("EC")
    if ec is not None and params["EC"]["threshold"] > 0:
        p = params["EC"]
        traces["EC"] = eq.score_ec(ec, p["threshold"], p["slope"], p["intercept"],
                                   p["rise_slope"], p["rise_limit"], p["basis"])

    sar = value("SAR")
    if sar is not None and ec is not None:
        basis = model.switch("sar_ec_basis", "saturation_paste")
        ec_basis = ec if basis == "as_reported" else to_saturation_basis(ec, factors, params)
        traces["SAR"] = eq.score_sar(sar, ec_basis, params["SAR"])

    if (x := value("SOC")) is not None:
        traces["SOC"] = eq.score_soc(x, **params["SOC"])
    if (x := value("MBC")) is not None:
        traces["MBC"] = eq.score_mbc(x, **params["MBC"])
    if (x := value("PMN")) is not None:
        traces["PMN"] = eq.score_pmn(x, **params["PMN"])
    if (x := value("BG")) is not None:
        traces["BG"] = eq.score_bg(x, **params["BG"])

    return traces


def _factors_by_site(factors, names: Sequence[str]) -> dict[str, SiteFactors]:
    """One description per site, however the caller supplied them.

    A single ``SiteFactors`` means every site shares one description, which is
    the ordinary case and stays exactly as it was. A mapping means the sites
    were described separately, and then every one of them has to be there: a
    site quietly falling back on another site's soil would be the same
    scientific error as a default factor class, only harder to notice.
    """
    if isinstance(factors, SiteFactors):
        return {name: factors for name in names}
    if isinstance(factors, Mapping):
        missing = [name for name in names if name not in factors]
        if missing:
            raise ParameterError(
                "No factor classes were chosen for "
                + ", ".join(f"'{name}'" for name in missing)
                + ". Every site has to be described before anything is "
                "scored, because the description decides which curves its "
                "samples are scored against."
            )
        return {name: factors[name] for name in names}
    raise TypeError(
        "factors must be a SiteFactors or a mapping of site name to "
        f"SiteFactors, not {type(factors).__name__}."
    )


def aggregate(frame: pd.DataFrame, index_column: str) -> pd.DataFrame:
    """Summarise by land use x management x crop x depth.

    Descriptive statistics only.  The engine deliberately stops short of
    significance testing: a difference between two group means here is a
    description of the samples, not evidence of an effect.

    Site is not one of the keys, deliberately: the comparison a user wants
    from this table is between land uses and managements, and splitting it by
    site as well would break that comparison into one row per farm. But a
    group can then average samples from places described by different factor
    classes, so the sites that went into each row are named in a column of
    their own. The mean is still a mean of scores, which is what makes soils
    on different curves comparable at all -- the column is there so that no
    one has to guess what was pooled.
    """
    keys = [c for c in GROUPING_COLUMNS if c in frame.columns]
    numeric = [c for c in frame.columns
               if c.endswith(("_score", "_component")) or c == index_column]
    numeric = [c for c in numeric if pd.api.types.is_numeric_dtype(frame[c])]
    if not keys or not numeric:
        return pd.DataFrame()

    grouped = frame.groupby(keys, dropna=False)
    out = grouped[numeric].agg(["mean", "std", "min", "max", "count"])
    out.columns = [f"{col}_{stat}" for col, stat in out.columns]
    out = out.reset_index()

    if "site" in frame.columns and frame["site"].nunique() > 1:
        names = grouped["site"].agg(
            lambda values: ", ".join(sorted(set(values.astype(str))))).reset_index()
        names = names.rename(columns={"site": "sites"})
        out = out.merge(names, on=keys, how="left")
        out.insert(len(keys), "sites", out.pop("sites"))
    for column in out.columns:
        if column.endswith(("_mean", "_std", "_min", "_max")):
            out[column] = out[column].round(3)
    return out


def _collapse(messages: list[str]) -> list[str]:
    """Fold per-crop warnings that say the same thing into one line.

    Three identical sentences differing only in the crop name are noise; one
    sentence naming all three crops is information.
    """
    import re

    pattern = re.compile(r"^The crop '(?P<crop>[^']+)' (?P<rest>.+)$")
    grouped: dict[str, list[str]] = {}
    out: list[str] = []
    for message in messages:
        match = pattern.match(message)
        if match:
            grouped.setdefault(match.group("rest"), []).append(match.group("crop"))
        else:
            out.append(message)
    for rest, crops in grouped.items():
        if len(crops) == 1:
            out.append(f"The crop '{crops[0]}' {rest}")
        else:
            names = ", ".join(f"'{c}'" for c in crops[:-1]) + f" and '{crops[-1]}'"
            out.append(f"The crops {names} {_pluralise(rest)}")
    return out


def _pluralise(rest: str) -> str:
    if rest.startswith("has "):
        rest = "have " + rest[4:]
    return rest.replace(" for it.", " for them.")


def _suggest(name: str) -> list[str]:
    from .crops import suggest_crops
    return suggest_crops(name)


class NoIndicatorsError(ValueError):
    """Raised when a dataset contains nothing that can be scored."""
