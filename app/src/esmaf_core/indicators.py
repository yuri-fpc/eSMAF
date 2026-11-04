"""Indicator registry.

A single place that answers, for every soil health indicator eSMAF knows
about: what it is called, which component it belongs to, in which unit it
must be supplied, which shape its scoring curve has, and which spellings of
its column header the importer should recognise.

Nothing here computes anything.  Keeping the metadata separate from the
equations is what lets the interface explain a decision (unit, curve type,
affected factor classes) without reaching into the maths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Component = Literal["physical", "chemical", "biological"]
CurveShape = Literal["more_is_better", "less_is_better", "optimal_range"]


@dataclass(frozen=True)
class Indicator:
    """Static description of one soil health indicator."""

    key: str                      # internal identifier, e.g. "BD"
    label: str                    # human-readable name
    component: Component
    unit: str                     # unit the engine expects
    curve: CurveShape
    canonical_column: str         # header written in the eSMAF template
    aliases: tuple[str, ...] = ()  # other spellings accepted on import
    plausible: tuple[float, float] = (0.0, 1e9)  # soft range for validation
    hard_limits: tuple[float, float] = (-1e9, 1e9)  # values outside are errors
    factors: tuple[str, ...] = ()  # factor classes that change this curve
    note: str = ""                # shown as contextual help in the interface
    reference: str = ""

    @property
    def score_column(self) -> str:
        return f"{self.key}_score"


#: WFPS is the one indicator that produces two scores from one measurement,
#: exactly as in the original SMAF: one for biological activity and one for
#: environmental (denitrification) protection.
WFPS_SUBSCORES = ("WFPS_BiolAct", "WFPS_EnvProtect")


INDICATORS: tuple[Indicator, ...] = (
    # ------------------------------------------------------------------ physical
    Indicator(
        key="BD",
        label="Bulk density",
        component="physical",
        unit="g cm-3",
        curve="less_is_better",
        canonical_column="BD_g/cm3",
        aliases=("BD_g/cm³", "BD", "bulk_density", "dens", "DENS", "DENS_g/cm³",
                 "DENS_g/cm3", "dens_g/cm3", "densidade", "Ds", "BD_gcm3"),
        plausible=(0.6, 2.0),
        hard_limits=(0.1, 3.0),
        factors=("texture", "mineral"),
        note=(
            "Weibull function. Below texture class 4 the curve is taken directly "
            "from the texture table; from class 4 upwards it is additionally "
            "shifted by the dominant clay mineralogy."
        ),
        reference="Grossman et al. (2001); Andrews et al. (2004)",
    ),
    Indicator(
        key="AGG",
        label="Macroaggregate stability",
        component="physical",
        unit="%",
        curve="more_is_better",
        canonical_column="AGG_pct",
        aliases=("AGG", "AGS", "AGS_pct", "AGG_pct", "aggregate_stability", "agg",
                 "DMP", "WSA", "estabilidade_agregados"),
        plausible=(0.0, 100.0),
        hard_limits=(0.0, 100.0),
        factors=("organic_matter", "texture", "iron_oxide"),
        note=(
            "Sinusoidal limit function that saturates at 50 %: every sample above "
            "50 % water-stable aggregates scores 1.00. In strongly aggregated "
            "tropical soils this indicator often loses its ability to separate "
            "treatments."
        ),
        reference="USDA (1966); Andrews et al. (2004)",
    ),
    Indicator(
        key="WFPS",
        label="Water-filled pore space",
        component="physical",
        unit="fraction (0-1)",
        curve="optimal_range",
        canonical_column="WFPS_fraction",
        aliases=("WFPS", "WFPS_pct", "wfps", "water_filled_pore_space", "EPPA"),
        plausible=(0.0, 1.0),
        hard_limits=(0.0, 1.0),
        factors=("texture",),
        note=(
            "Supplied as a FRACTION between 0 and 1, not as a percentage: "
            "WFPS = (gravimetric water content x BD) / (1 - BD/2.65). "
            "Produces two scores, biological activity and environmental "
            "protection, which share the indicator weight equally. "
            "SMAF describes this indicator as transitory; it reflects the "
            "moment of sampling more than the condition of the soil."
        ),
        reference="Doran et al. (1990); Andrews et al. (2004)",
    ),
    Indicator(
        key="AWC",
        label="Available water capacity",
        component="physical",
        unit="g H2O g-1 soil",
        curve="more_is_better",
        canonical_column="AWC_gH2O/gSoil",
        aliases=("AWC", "awc", "available_water_capacity", "CAD",
                 # Volumetric water capacity, converted with the field bulk
                 # density of the same sample once the unit is confirmed.
                 "AWC_cm3/cm3", "AWC_cm³/cm³", "AWC_cm3cm3", "AWC_vol",
                 "CAD_cm3/cm3", "AWC_m3/m3"),
        plausible=(0.0, 0.6),
        hard_limits=(0.0, 1.0),
        factors=("region", "texture", "organic_matter"),
        note=(
            "Two different functions are used: a Morgan-Mercer-Flodin curve in "
            "arid regions and a sinusoidal curve in humid regions. The region "
            "class therefore changes the shape of the curve, not merely its "
            "parameters."
        ),
        reference="Diaz-Zorita et al. (1999)",
    ),
    # ------------------------------------------------------------------ chemical
    Indicator(
        key="pH",
        label="Soil solution pH",
        component="chemical",
        unit="-",
        curve="optimal_range",
        canonical_column="pH_H2O",
        aliases=("ph", "pH", "pH_H2O", "pH_water", "pH_CaCl2", "pH_KCl",
                 "pH_agua", "pH_água", "pH_CaCl2_0.01M"),
        plausible=(3.0, 10.0),
        hard_limits=(0.0, 14.0),
        factors=("crop",),
        note=(
            "Gaussian curve centred on the pH optimum of the selected crop, with "
            "a width taken from the crop's tolerated range. Crop choice is the "
            "only factor acting on this indicator, which makes it the indicator "
            "most sensitive to picking the right entry in the crop database."
        ),
        reference="Whittaker (1955); Andrews et al. (2004)",
    ),
    Indicator(
        key="P",
        label="Extractable phosphorus",
        component="chemical",
        unit="mg kg-1",
        curve="optimal_range",
        canonical_column="P_mg/kg",
        aliases=("P", "p", "P_mgkg", "soil_P", "P_disponivel", "fosforo",
                 # Brazilian laboratories report P per volume of sieved soil.
                 # The header is recognised, the unit is confirmed by the user,
                 # and the conversion happens in the engine.
                 "P_mg/dm3", "P_mg/dm³", "P_mgdm3", "P_mg_dm3", "P resina",
                 "P_resina", "P_mg/L"),
        plausible=(0.0, 400.0),
        hard_limits=(0.0, 5000.0),
        factors=("p_method", "weathering", "organic_matter", "texture", "slope", "crop"),
        note=(
            "The only indicator scored against two opposing criteria: an "
            "agronomic sufficiency curve at low P and an environmental loss-risk "
            "curve at high P, with a plateau of score 1.00 in between. The "
            "measured value is first multiplied by a method factor that depends "
            "jointly on the extraction method and the weathering class."
        ),
        reference="Sharpley (1991); Andrews et al. (2004)",
    ),
    Indicator(
        key="K",
        label="Exchangeable potassium",
        component="chemical",
        unit="mg kg-1",
        curve="more_is_better",
        canonical_column="K_mg/kg",
        aliases=("K", "k", "K_mgkg", "exch_K", "potassio",
                 "K_mg/dm3", "K_mg/dm³", "K_mgdm3", "K_mg_dm3", "K_mg/L"),
        plausible=(0.0, 800.0),
        hard_limits=(0.0, 10000.0),
        factors=("texture",),
        note=(
            "Exponential rise to a plateau. SMAF uses two parameter sets, one "
            "for coarse and one for fine textures; eSMAF additionally offers a "
            "curve calibrated for Brazilian conditions after IAC Boletim 100."
        ),
        reference="Andrews et al. (2004); IAC (2022)",
    ),
    Indicator(
        key="SAR",
        label="Sodium adsorption ratio",
        component="chemical",
        unit="(mmol L-1)^0.5",
        curve="less_is_better",
        canonical_column="SAR",
        aliases=("SAR", "sar", "SAR_pct", "RAS"),
        plausible=(0.0, 40.0),
        hard_limits=(0.0, 200.0),
        factors=("ec_method",),
        note=(
            "SAR is a ratio, not a percentage. Which of three polynomials is "
            "used depends on the electrical conductivity of the SATURATION "
            "PASTE; when EC was measured at 1:1 it is converted before the "
            "branch is chosen. Requires EC to be present in the same row."
        ),
        reference="Hanson & Grattan (1992), after Rhoades (1977)",
    ),
    Indicator(
        key="EC",
        label="Electrical conductivity",
        component="chemical",
        unit="dS m-1",
        curve="less_is_better",
        canonical_column="EC_dS/m",
        aliases=("EC", "ec", "EC_dSm", "CE", "condutividade"),
        plausible=(0.0, 20.0),
        hard_limits=(0.0, 200.0),
        factors=("ec_method", "texture", "crop"),
        note=(
            "Plateau function: a rising limb at very low EC, a plateau of 1.00, "
            "then a linear decline past the salinity threshold of the selected "
            "crop. Threshold and slope both come from the crop database."
        ),
        reference="Smith & Doran (1996); Andrews et al. (2004)",
    ),
    # ---------------------------------------------------------------- biological
    Indicator(
        key="SOC",
        label="Soil organic carbon",
        component="biological",
        unit="%",
        curve="more_is_better",
        canonical_column="SOC_pct",
        aliases=("SOC", "soc", "SOC_pct", "TOC", "TOC_pct", "COT",
                 "carbono_organico", "C_org", "C", "C_pct", "SOC_g/kg",
                 "SOC_gkg", "COT_g/kg", "C_org_g/kg",
                 # Organic MATTER, which a Brazilian report gives instead of
                 # carbon. Recognised as the same column; which of the two it
                 # is, and in which unit, is declared rather than guessed.
                 "MO", "M.O.", "MO_pct", "MO_g/dm3", "MO_g/kg", "OM", "SOM",
                 "materia_organica", "matéria_orgânica", "organic_matter"),
        plausible=(0.0, 20.0),
        hard_limits=(0.0, 60.0),
        factors=("organic_matter", "texture", "climate"),
        note=(
            "Logistic curve. The inherent organic matter class is the dominant "
            "factor: the same measured carbon content scores very differently "
            "in a soil whose natural condition is carbon-rich and in one whose "
            "natural condition is carbon-poor."
        ),
        reference="Andrews et al. (2004)",
    ),
    Indicator(
        key="PMN",
        label="Potentially mineralizable nitrogen",
        component="biological",
        unit="mg kg-1",
        curve="more_is_better",
        canonical_column="PMN_mg/kg",
        aliases=("PMN", "pmn", "PMN(SOC)_pct", "soc_pmn", "SOC_PMN", "Nmin",
                 "N_mineralizavel", "PMN_mgkg"),
        plausible=(0.0, 60.0),
        hard_limits=(0.0, 500.0),
        factors=("organic_matter", "texture", "climate"),
        note=(
            "Logistic curve calibrated over roughly 0-45 mg kg-1. The previous "
            "eSMAF web template asked for PMN as a percentage of organic carbon "
            "and multiplied it by ten before scoring. This application asks for "
            "mg kg-1 and applies no such factor, so a column carried over from "
            "that template holds numbers about ten times smaller than the unit "
            "it will be declared in. Whether the percentage convention should be "
            "offered as a declarable unit is an open question for the authors "
            "(audit B6)."
        ),
        reference="Needelman et al. (1999); Jones et al. (1982)",
    ),
    Indicator(
        key="MBC",
        label="Microbial biomass carbon",
        component="biological",
        unit="mg kg-1",
        curve="more_is_better",
        canonical_column="MBC_mg/kg",
        aliases=("MBC", "mbc", "CBM", "MBC_mgkg", "biomassa_microbiana"),
        plausible=(0.0, 3000.0),
        hard_limits=(0.0, 20000.0),
        factors=("organic_matter", "texture", "season", "climate"),
        note=(
            "Logistic curve in mg kg-1 (SMAF changed these units from g kg-1 in "
            "a later revision). Season and climate act jointly through a single "
            "combined factor, because microbial biomass responds to when the "
            "sample was taken as much as to where."
        ),
        reference="Franzluebbers et al. (1996)",
    ),
    Indicator(
        key="BG",
        label="Beta-glucosidase activity",
        component="biological",
        unit="mg p-nitrophenol kg-1 h-1",
        curve="more_is_better",
        canonical_column="BG_mg/kg/h",
        aliases=("BG", "bg", "BG_ug/gh", "beta_glucosidase", "glucosidase"),
        plausible=(0.0, 800.0),
        hard_limits=(0.0, 10000.0),
        factors=("organic_matter", "texture", "climate"),
        note=(
            "Logistic curve; the measured activity is divided by 1000 inside the "
            "equation. Note that mg p-nitrophenol kg-1 h-1 and "
            "ug p-nitrophenol g-1 h-1 are numerically identical."
        ),
        reference="Stott et al. (2010)",
    ),
)

BY_KEY: dict[str, Indicator] = {ind.key: ind for ind in INDICATORS}

COMPONENTS: tuple[Component, ...] = ("physical", "chemical", "biological")

COMPONENT_LABELS = {
    "physical": "Physical",
    "chemical": "Chemical",
    "biological": "Biological",
}

#: Grouping columns that describe the sample rather than measure the soil.
#:
#: ``site`` is the one that changes the arithmetic. Every other column here
#: labels a sample; ``site`` says which physical place it came from, and each
#: place carries its own factor classes, so two rows with the same bulk density
#: can be scored against different curves. It is optional: a file without it is
#: one site, exactly as before.
CONTEXT_COLUMNS: tuple[str, ...] = (
    "site",
    "land_use",
    "management",
    "crop",
    "depth",
    "sample",
    "state",
    "city",
)

CONTEXT_ALIASES: dict[str, tuple[str, ...]] = {
    "site": ("Site", "site_name", "site_id", "site_type", "local", "lugar",
             "fazenda", "farm", "area", "área", "property", "propriedade",
             "field", "talhao", "talhão", "experiment", "experimento",
             "location", "localidade"),
    "land_use": ("Land_Use", "LandUse", "land use", "uso_da_terra", "uso"),
    "management": ("Management", "manejo", "management_practice"),
    "crop": ("Crop", "cultura", "vegetation", "vegetacao"),
    "depth": ("Depth", "profundidade", "layer", "camada"),
    "sample": ("Sample", "amostra", "rep", "replicate", "repeticao"),
    "state": ("State", "estado", "UF"),
    "city": ("City", "municipio", "município", "municipality"),
}


def indicators_for(component: Component) -> list[Indicator]:
    return [ind for ind in INDICATORS if ind.component == component]


def resolve_column(header: str) -> str | None:
    """Map a spreadsheet header onto an indicator key or a context column.

    Matching is deliberately forgiving about case, spaces, underscores and
    accents, because the alternative -- rejecting a column the user clearly
    meant -- costs more than the small risk of a wrong guess, and every guess
    is shown for confirmation before the analysis runs.
    """
    norm = _normalise(header)
    for ind in INDICATORS:
        candidates = (ind.key, ind.canonical_column, ind.label, *ind.aliases)
        if any(_normalise(c) == norm for c in candidates):
            return ind.key
    for ctx, aliases in CONTEXT_ALIASES.items():
        if any(_normalise(c) == norm for c in (ctx, *aliases)):
            return ctx
    return None


def suggest_column(header: str, limit: int = 3) -> list[str]:
    """Return the closest known headers, for a 'did you mean' message."""
    import difflib

    pool: dict[str, str] = {}
    for ind in INDICATORS:
        for c in (ind.canonical_column, ind.key, *ind.aliases):
            pool[_normalise(c)] = ind.canonical_column
    for ctx, aliases in CONTEXT_ALIASES.items():
        for c in (ctx, *aliases):
            pool[_normalise(c)] = ctx
    matches = difflib.get_close_matches(_normalise(header), list(pool), n=limit, cutoff=0.6)
    seen: list[str] = []
    for m in matches:
        target = pool[m]
        if target not in seen:
            seen.append(target)
    return seen


def _normalise(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    keep = [ch.lower() for ch in text if ch.isalnum()]
    return "".join(keep)
