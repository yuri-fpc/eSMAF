"""Factor classes: the site description that tunes every scoring curve.

The original SMAF spreadsheet presents these as bare numbers in a lookup
table.  That is where most of the interpretation risk in SMAF lives: the same
measured value can score anywhere between 0.2 and 1.0 depending on which
organic matter class the user picked.  So each class here carries the text
the interface needs to make that decision visible -- what it means, which
indicators it moves, and where the classification comes from.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FactorOption:
    code: int
    label: str
    detail: str = ""


@dataclass(frozen=True)
class Factor:
    key: str
    label: str
    group: str                    # environmental | soil | method
    question: str                 # asked in the interface
    why: str                      # why this factor matters
    affects: tuple[str, ...]      # indicator keys whose curve it changes
    options: tuple[FactorOption, ...]
    reference: str = ""
    required: bool = True

    def option(self, code: int) -> FactorOption:
        for opt in self.options:
            if opt.code == code:
                return opt
        raise KeyError(f"{self.label}: no class with code {code}")

    @property
    def codes(self) -> tuple[int, ...]:
        return tuple(o.code for o in self.options)


FACTORS: tuple[Factor, ...] = (
    # ------------------------------------------------------- environmental
    Factor(
        key="region",
        label="Region",
        group="environmental",
        question="Is the site in an arid or a humid region?",
        why=(
            "Available water capacity is scored with a different function in each "
            "region, so this choice changes the shape of the AWC curve rather "
            "than only its parameters."
        ),
        affects=("AWC",),
        options=(
            FactorOption(1, "Arid region", "Annual precipitation at or below the arid threshold (USDA LRR B-J)."),
            FactorOption(2, "Humid region", "Annual precipitation above the arid threshold (USDA LRR A, K-V)."),
        ),
        reference="Diaz-Zorita et al. (1999)",
    ),
    Factor(
        key="season",
        label="Sampling season",
        group="environmental",
        question="In which season, relative to the crop cycle, was the soil sampled?",
        why=(
            "Microbial biomass swings widely over a season. SMAF corrects for "
            "this by combining season with climate into a single factor, so "
            "that samples taken at different moments remain comparable."
        ),
        affects=("MBC",),
        options=(
            FactorOption(1, "Spring - pre-planting or at planting", "Reference season; no climate correction is applied."),
            FactorOption(2, "Summer - mid-growing season", ""),
            FactorOption(3, "Autumn - at or just after harvest", ""),
            FactorOption(4, "Winter - fallow, cover crop or double crop", ""),
        ),
        reference="Franzluebbers et al. (1996)",
    ),
    Factor(
        key="climate",
        label="Climate",
        group="environmental",
        question="How do sunny days and annual rainfall combine at this site?",
        why=(
            "Climate sets how much carbon and biological activity a soil can be "
            "expected to hold, and therefore what counts as a good score for "
            "the biological indicators."
        ),
        affects=("SOC", "BG", "PMN", "MBC"),
        options=(
            FactorOption(1, "High / high", "170 sunny days or more and 550 mm or more of annual precipitation."),
            FactorOption(2, "High / low", "170 sunny days or more and less than 550 mm of annual precipitation."),
            FactorOption(3, "Low / high", "Fewer than 170 sunny days and 550 mm or more of annual precipitation."),
            FactorOption(4, "Low / low", "Fewer than 170 sunny days and less than 550 mm of annual precipitation."),
        ),
        reference="STATSGO / US Soil Survey",
    ),
    Factor(
        key="slope",
        label="Slope",
        group="environmental",
        question="What is the slope of the sampling site?",
        why=(
            "Slope sets the phosphorus concentration above which the "
            "environmental loss-risk limb of the P curve begins. On steep "
            "ground the penalty for excess P starts earlier."
        ),
        affects=("P",),
        options=(
            FactorOption(1, "0 to less than 2 %", ""),
            FactorOption(2, "2 to less than 5 %", ""),
            FactorOption(3, "5 to less than 9 %", ""),
            FactorOption(4, "9 to less than 15 %", ""),
            FactorOption(5, "15 % or more", ""),
        ),
        reference="Sharpley (1991)",
    ),
    # ---------------------------------------------------------------- soil
    Factor(
        key="texture",
        label="Texture",
        group="soil",
        question="Which textural class describes the sampled layer?",
        why=(
            "Texture enters more scoring curves than any other factor. It is "
            "also the factor where the eSMAF website departed from SMAF: it "
            "offered four classes where SMAF defines five, so clays above 60 % "
            "were scored with the parameters of a lighter soil."
        ),
        affects=("BD", "AGG", "WFPS", "AWC", "SOC", "MBC", "BG", "PMN", "EC", "P", "K"),
        options=(
            FactorOption(1, "Coarse", "Sand, loamy sand, or sandy loam with less than 8 % clay."),
            FactorOption(2, "Medium", "Sandy loam with more than 8 % clay, sandy clay loam, or loam."),
            FactorOption(3, "Silty", "Silt loam or silt."),
            FactorOption(4, "Fine", "Sandy clay, clay loam, silty clay loam, silty clay, or clay with less than 60 % clay."),
            FactorOption(5, "Very fine", "Clay with more than 60 % clay. Common in Brazilian Oxisols."),
        ),
        reference="Quisenberry et al. (1993); Andrews et al. (2004)",
    ),
    Factor(
        key="mineral",
        label="Clay mineralogy",
        group="soil",
        question="Which mineral dominates the clay fraction?",
        why=(
            "In fine-textured soils the bulk density expected of a healthy soil "
            "depends on which clay dominates, because smectites and short-range "
            "order clays pack very differently from kaolinite."
        ),
        affects=("BD",),
        options=(
            FactorOption(1, "Smectitic", "Clay fraction dominated by smectites (2:1 expanding clays)."),
            FactorOption(2, "Glassy / short-range order", "Allophane, imogolite and similar low-crystallinity phases."),
            FactorOption(3, "Other clays", "Kaolinite and other 1:1 clays; the usual choice for weathered tropical soils."),
        ),
        reference="Grossman et al. (2001)",
        required=False,
    ),
    Factor(
        key="organic_matter",
        label="Inherent organic matter class",
        group="soil",
        question="What organic matter level is INHERENT to this soil type?",
        why=(
            "This is the single most influential factor in SMAF and the one most "
            "often misread. It does not describe the organic matter you measured; "
            "it describes the organic matter this soil type would hold in its "
            "natural condition, and it is read from the soil classification. "
            "Getting it wrong shifts every biological score."
        ),
        affects=("AGG", "AWC", "SOC", "MBC", "BG", "PMN", "P"),
        options=(
            FactorOption(
                1, "Very high",
                "Soil Taxonomy: all Histosols; Andisols, Oxisols and Spodosols with aquic regime; "
                "Turbels and Histels. SiBCS: Organossolos; Cambissolos Hísticos.",
            ),
            FactorOption(
                2, "High",
                "Soil Taxonomy: all Mollisols; humid-region Andisols; Inceptisols with aquic regime; "
                "Humults; Oxisols with udic regime. SiBCS: Chernossolos; Cambissolos Húmicos; "
                "Gleissolos Melânicos; Latossolos Brunos; Nitossolos Brunos.",
            ),
            FactorOption(
                3, "Moderate",
                "Soil Taxonomy: all Alfisols; Anthrepts; Entisols with aquic regime. "
                "SiBCS: Latossolos Amarelos, Vermelhos e Vermelho-amarelos; Argissolos; "
                "Cambissolos Háplicos; Nitossolos Vermelhos.",
            ),
            FactorOption(
                4, "Low",
                "Soil Taxonomy: all Aridisols; Orthents; Psamments; Udults and Ustults; "
                "Oxisols with ustic or torric regime. SiBCS: Neossolos; Plintossolos; "
                "Planossolos; Luvissolos; Espodossolos.",
            ),
        ),
        reference="Soil Taxonomy; Embrapa (2013) SiBCS",
    ),
    Factor(
        key="iron_oxide",
        label="Iron oxide class",
        group="soil",
        question="Does the soil have a textural B horizon with low base saturation?",
        why=(
            "Free iron oxides cement aggregates, so the aggregate stability "
            "expected of a healthy soil is higher in these soils."
        ),
        affects=("AGG",),
        options=(
            FactorOption(
                1, "Ultisols and equivalents",
                "Soil Taxonomy: Ultisols, i.e. argillic or kandic horizon with low base saturation, "
                "any moisture and temperature regime except aridic. SiBCS: Argissolos and Planossolos.",
            ),
            FactorOption(2, "All other soil orders", ""),
        ),
        reference="Andrews et al. (2004)",
    ),
    Factor(
        key="weathering",
        label="Weathering class",
        group="soil",
        question="How weathered is the soil, and does it contain carbonates?",
        why=(
            "Weathering governs how much of the phosphorus recovered by an "
            "extractant is actually available, and so acts together with the "
            "extraction method on the P method factor."
        ),
        affects=("P",),
        options=(
            FactorOption(1, "Carbonate phase present", "Calcareous soils."),
            FactorOption(
                2, "Highly weathered",
                "1:1 clays with oxides and hydroxides of Fe and Al: Ultisols, Oxisols, acidic Ochrepts. "
                "The usual choice for Latossolos.",
            ),
            FactorOption(3, "All other soils", "Slightly weathered."),
        ),
        reference="Sharpley (1991), SSSAJ 55:1038",
    ),
    # -------------------------------------------------------------- method
    Factor(
        key="p_method",
        label="Phosphorus extraction method",
        group="method",
        question="Which extractant produced the reported phosphorus values?",
        why=(
            "Extractants recover very different fractions of soil P. The measured "
            "value is multiplied by a factor that depends on the method AND on "
            "the weathering class before it reaches the scoring curve, so a "
            "mismatch here moves the P score more than a laboratory error would."
        ),
        affects=("P",),
        options=(
            FactorOption(1, "Mehlich 1", ""),
            FactorOption(2, "Mehlich 3", ""),
            FactorOption(3, "Bray", ""),
            FactorOption(4, "Olsen", ""),
            FactorOption(5, "Ion exchange resin", "The routine method in Brazilian laboratories."),
            FactorOption(6, "Iron oxide strip", ""),
        ),
        reference="Sharpley (1991); Andrews et al. (2004)",
    ),
    Factor(
        key="ec_method",
        label="Electrical conductivity method",
        group="method",
        question="How was electrical conductivity measured?",
        why=(
            "The salinity threshold of a crop is defined on a saturation paste. "
            "A 1:1 extract reads roughly 1.77 times lower, with a further "
            "texture correction, so the threshold has to be rescaled. The same "
            "conversion decides which branch of the SAR curve applies."
        ),
        affects=("EC", "SAR"),
        options=(
            FactorOption(1, "Saturation paste", ""),
            FactorOption(2, "1:1 soil:water ratio", ""),
        ),
        reference="Smith & Doran (1996)",
    ),
)

BY_KEY: dict[str, Factor] = {f.key: f for f in FACTORS}

GROUPS = (
    ("environmental", "Environmental factors"),
    ("soil", "Soil factors"),
    ("method", "Method factors"),
)


def factors_in(group: str) -> list[Factor]:
    return [f for f in FACTORS if f.group == group]


def factors_affecting(indicator_key: str) -> list[Factor]:
    return [f for f in FACTORS if indicator_key in f.affects]


def required_for(indicator_keys: set[str]) -> list[Factor]:
    """Only ask for the factor classes the selected indicators actually use."""
    needed = []
    for f in FACTORS:
        if set(f.affects) & indicator_keys:
            needed.append(f)
    return needed


def describe(selection: dict[str, int]) -> list[tuple[str, str]]:
    """Render a selection as (factor label, chosen class label) for reports."""
    rows = []
    for f in FACTORS:
        if f.key in selection:
            rows.append((f.label, f"{selection[f.key]} - {f.option(selection[f.key]).label}"))
    return rows


UNUSUAL_COMBINATIONS: tuple[tuple[str, str], ...] = (
    (
        "weathering==1 and p_method==5",
        "Resin-extracted phosphorus is rarely reported for calcareous soils. "
        "Check that the weathering class matches the site.",
    ),
    (
        "texture>=4 and mineral is None",
        "Clay mineralogy is used to score bulk density in fine-textured soils. "
        "Without it the bulk density score falls back to the 'other clays' set.",
    ),
    (
        "organic_matter==1 and climate in (2, 4)",
        "A very high inherent organic matter class is unusual in a low-rainfall "
        "climate. Confirm the class was read from the soil classification and "
        "not from the measured carbon content.",
    ),
    (
        "region==1 and climate==1",
        "An arid region combined with a high-rainfall climate class is "
        "contradictory. Review both selections.",
    ),
)
