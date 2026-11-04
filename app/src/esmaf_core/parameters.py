"""Resolve site factor classes and crop into equation parameters.

This is the layer the original SMAF spreadsheet hides inside lookup formulas.
Exposing it explicitly means the interface can show, for any score, exactly
which factor tables were consulted and what each contributed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .crops import Crop
from .models import Model


@dataclass(frozen=True)
class SiteFactors:
    """The user's factor class selection for one analysis.

    Every field starts empty on purpose. A default here would be a scientific
    decision made on the user's behalf and then hidden from them: the same
    measurements score very differently under a different organic matter or
    texture class, so the analysis refuses to run until each one has been
    chosen deliberately.
    """

    region: int | None = None
    season: int | None = None
    climate: int | None = None
    slope: int | None = None
    texture: int | None = None
    mineral: int | None = None
    organic_matter: int | None = None
    iron_oxide: int | None = None
    weathering: int | None = None
    p_method: int | None = None
    ec_method: int | None = None

    @property
    def missing(self) -> list[str]:
        return [key for key, value in self.as_dict().items() if value is None]

    @property
    def complete(self) -> bool:
        return not self.missing

    def as_dict(self) -> dict[str, int]:
        return {
            "region": self.region, "season": self.season, "climate": self.climate,
            "slope": self.slope, "texture": self.texture, "mineral": self.mineral,
            "organic_matter": self.organic_matter, "iron_oxide": self.iron_oxide,
            "weathering": self.weathering, "p_method": self.p_method,
            "ec_method": self.ec_method,
        }

    def require(self, *keys: str) -> None:
        """Raise if any of these factor classes was not chosen."""
        absent = [k for k in keys if getattr(self, k) is None]
        if absent:
            names = ", ".join(k.replace("_", " ") for k in absent)
            raise ParameterError(
                f"These factor classes have not been selected yet: {names}. "
                "Choose them on the Setup page; nothing is assumed by default "
                "because the choice changes the scores."
            )

    @property
    def season_climate_code(self) -> str:
        """SMAF combines season and climate into one key, spring excepted."""
        if self.season == 1:
            return "1"
        return f"{self.season}.{self.climate}"

    @property
    def p_method_code(self) -> str:
        """P method and weathering class form one combined key.

        Kept as a string on purpose: the web version built this key by adding
        a float (``method + weathering/10``), which is exact for these values
        today but silently fragile.
        """
        return f"{self.p_method}.{self.weathering}"


@dataclass
class ResolvedParameters:
    """Everything the equations need, plus a record of where it came from."""

    values: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    def __contains__(self, key: str) -> bool:
        return key in self.values

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


def _pick(table: dict, code: int | str, what: str, params: ResolvedParameters,
          indicator: str) -> Any:
    key = str(code)
    if key not in table:
        raise ParameterError(
            f"{indicator}: no entry for {what} class {key}. "
            f"This model defines classes {', '.join(sorted(table))}."
        )
    params.provenance.setdefault(indicator, {})[what] = {"class": key, "value": table[key]}
    return table[key]


class ParameterError(ValueError):
    """Raised when a factor class has no entry in the active model."""


def resolve(model: Model, factors: SiteFactors, crop: Crop) -> ResolvedParameters:
    """Build the full parameter set for one crop under one set of factors."""
    p = ResolvedParameters()
    v = p.values
    factors.require("region", "season", "climate", "slope", "texture", "mineral",
                    "organic_matter", "iron_oxide", "weathering", "p_method",
                    "ec_method")
    tx = str(factors.texture)

    if factors.texture > model.texture_classes:
        raise ParameterError(
            f"Texture class {factors.texture} is not defined in model "
            f"'{model.id}', which has {model.texture_classes} classes."
        )

    # --- AGG -------------------------------------------------------------
    t = model.table("AGG")
    v["AGG"] = {
        "a": t["a"], "b": t["b"], "c": t["c"],
        "d": (_pick(t["d_organic_matter"], factors.organic_matter, "organic matter", p, "AGG")
              * _pick(t["d_texture"], tx, "texture", p, "AGG")
              * _pick(t["d_iron_oxide"], factors.iron_oxide, "iron oxide", p, "AGG")),
        "saturates_at": t["saturates_at"],
    }

    # --- BD --------------------------------------------------------------
    t = model.table("BD")
    tx_row = _pick(t["texture"], tx, "texture", p, "BD")
    if factors.texture >= t["mineral_from_texture_class"]:
        min_row = _pick(t["mineral"], factors.mineral, "mineral", p, "BD")
        shifted_lo = tx_row["range_lo"] + min_row["range_shift"]
        v["BD"] = {
            "a": t["a"],
            "b": tx_row["b1"] + min_row["delta_b"],
            "c": t["c2_scale"] * pow(2.718281828459045, t["c2_exp"] * shifted_lo),
            "d": t["d2_intercept"] + t["d2_slope"] * shifted_lo,
        }
    else:
        v["BD"] = {"a": t["a"], "b": tx_row["b1"], "c": tx_row["c1"], "d": tx_row["d1"]}

    # --- WFPS ------------------------------------------------------------
    t = model.table("WFPS")
    bio = t["biological_activity"]
    v["WFPS_BiolAct"] = {
        "a": _pick(bio["a"], tx, "texture", p, "WFPS"),
        "b": bio["b"][tx], "c": bio["c"][tx],
    }
    v["WFPS_EnvProtect"] = dict(t["environmental_protection"])

    # --- AWC -------------------------------------------------------------
    t = model.table("AWC")
    if factors.region == 1:
        arid = t["arid"]
        v["AWC"] = {
            "region": "arid",
            "a": arid["a"], "c": arid["c"], "d": arid["d"],
            "b": (_pick(arid["b1_texture"], tx, "texture", p, "AWC")
                  * _pick(arid["b2_organic_matter"], factors.organic_matter,
                          "organic matter", p, "AWC")),
        }
    else:
        humid = t["humid"]
        v["AWC"] = {
            "region": "humid",
            "a": humid["a"], "b": humid["b"], "c": humid["c"],
            "d": _pick(humid["d_texture"], tx, "texture", p, "AWC"),
        }

    # --- pH --------------------------------------------------------------
    t = model.table("pH")
    v["pH"] = {"a": t["a"], "b": crop.ph_optimum, "c": crop.ph_range}
    p.provenance["pH"] = {"crop": {"name": crop.name,
                                   "optimum": crop.ph_optimum,
                                   "range": crop.ph_range}}
    if crop.ph_range <= 0:
        p.warnings.append(
            f"The crop '{crop.name}' has no pH tolerance range in the crop "
            "database, so the pH score cannot be computed."
        )

    # --- K ---------------------------------------------------------------
    t = model.table("K")
    if model.switch("k_curve") == "smaf_texture":
        smaf = t["smaf_texture"]
        coarse = factors.texture in smaf["coarse_texture_classes"]
        row = smaf["coarse"] if coarse else smaf["fine"]
        v["K"] = {"a": row["a"], "b": row["b"]}
        p.provenance["K"] = {"texture": {"class": tx,
                                         "curve": "coarse" if coarse else "fine"}}
    else:
        v["K"] = dict(t["brazil_iac2022"])
        p.provenance["K"] = {"calibration": {"source": "IAC Boletim 100 (2022)"}}

    # --- P ---------------------------------------------------------------
    t = model.table("P")
    method_key = factors.p_method_code
    if method_key not in t["method_factor"]:
        raise ParameterError(
            f"P: no method factor for extraction method {factors.p_method} "
            f"combined with weathering class {factors.weathering}."
        )
    v["P"] = {
        "method_factor": t["method_factor"][method_key],
        "crop_max": crop.p_max,
        "crop_fcrop": crop.p_crop_factor,
        "sufficiency": t["sufficiency"],
        "environmental": t["environmental"],
        "b_om": _pick(t["b_organic_matter"], factors.organic_matter, "organic matter", p, "P"),
        "b_tx": _pick(t["b_texture"], tx, "texture", p, "P"),
        "c_om": _pick(t["c_organic_matter"], factors.organic_matter, "organic matter", p, "P"),
        "c_tx": _pick(t["c_texture"], tx, "texture", p, "P"),
        "slope_threshold": _pick(t["slope_threshold"], factors.slope, "slope", p, "P"),
        "slope_factor": _pick(t["slope_factor"], factors.slope, "slope", p, "P"),
    }
    p.provenance.setdefault("P", {})["method"] = {
        "key": method_key, "factor": t["method_factor"][method_key],
        "meaning": "P extraction method x weathering class",
    }

    # --- SAR -------------------------------------------------------------
    v["SAR"] = model.table("SAR")

    # --- EC --------------------------------------------------------------
    t = model.table("EC")
    dt = crop.ec_decline_rate
    num = t["m_numerator"]
    den = t["m_denominator"]
    denominator = den[0] + den[1] * dt + den[2] * dt * dt
    m = (num[0] + num[1] * dt) / denominator if denominator else 0.0
    if factors.ec_method == 1:
        threshold = crop.ec_threshold_saturation
        rise = t["saturation_paste"]
        basis = "saturation paste"
    else:
        tex_corr = _pick(t["texture_correction"], tx, "texture", p, "EC")
        threshold = (crop.ec_threshold_saturation / t["ratio_1_1"]["divisor"]) * tex_corr
        rise = t["ratio_1_1"]
        basis = "1:1 soil:water"
    v["EC"] = {
        "threshold": threshold, "slope": m, "intercept": 1.0 - m * threshold,
        "rise_slope": rise["rise_slope"], "rise_limit": rise["rise_limit"],
        "basis": basis,
        "saturation_divisor": t["ratio_1_1"]["divisor"],
    }
    p.provenance["EC"] = {"crop": {"name": crop.name, "T_saturation": crop.ec_threshold_saturation,
                                   "dT": dt}, "method": {"basis": basis}}
    if crop.ec_from:
        p.provenance["EC"]["crop"]["parameters_taken_from"] = crop.ec_from
        p.warnings.append(
            f"The salinity parameters used for '{crop.name}' were taken from "
            f"'{crop.ec_from}', as set in the EC_FROM column of the crop "
            "database. The EC score therefore rests on that entry, not on one "
            "measured for this crop."
        )
    elif crop.ec_threshold_saturation <= 0:
        p.warnings.append(
            f"The crop '{crop.name}' has no salinity threshold in the crop "
            "database, so the EC score cannot be computed. If another entry's "
            "threshold is appropriate for it, name that entry in the EC_FROM "
            "column of the crop database."
        )

    # --- SOC, BG, PMN (additive c) and MBC (multiplicative c) ------------
    for key in ("SOC", "BG", "PMN", "MBC"):
        t = model.table(key)
        c1 = _pick(t["c_organic_matter"], factors.organic_matter, "organic matter", p, key)
        c2 = _pick(t["c_texture"], tx, "texture", p, key)
        if key == "MBC":
            table_name = ("c_season_climate_coarse"
                          if factors.texture == 1 and "c_season_climate_coarse" in t
                          else "c_season_climate")
            c3 = _pick(t[table_name], factors.season_climate_code, "season x climate", p, key)
            c = c1 * c2 * c3
        else:
            c3 = _pick(t["c_climate"], factors.climate, "climate", p, key)
            c = (c1 * c2) + (c1 * c2 * c3)
        entry = {"a": t["a"], "b": t["b"], "c": c}
        if "divisor" in t:
            entry["divisor"] = t["divisor"]
        v[key] = entry

    return p


def to_saturation_basis(ec_value: float, factors: SiteFactors,
                        params: ResolvedParameters) -> float:
    """Express a reported EC on a saturation-paste basis.

    The SAR branch thresholds are defined for saturation-paste EC.  A 1:1
    reading is roughly 1.77 times lower, so it has to be scaled up before the
    branch is chosen; the web version compared the reported value directly,
    which pushed 1:1 measurements into the wrong branch.
    """
    if factors.ec_method == 1:
        return ec_value
    divisor = params.get("EC", {}).get("saturation_divisor", 1.77)
    return ec_value * divisor
