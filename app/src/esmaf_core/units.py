"""The unit each measurement arrived in, and what it takes to use it.

SMAF's curves are built on one basis per indicator: phosphorus and potassium
per kilogram of soil, organic carbon as a percentage of mass, pH read in
water. A routine Brazilian laboratory report answers a different set of
conventions -- phosphorus per cubic decimetre, potassium in millimoles of
charge, organic *matter* rather than carbon, pH in calcium chloride -- and
none of those differences announces itself in the number.

The sizes involved are not rounding. Organic matter of 3.7 g dm-3 typed into
a column that expects carbon in per cent scores 0.99 where the honest value
scores 0.03. Potassium of 0.2 mmolc dm-3 read as mg kg-1 scores 0.00 where
7.8 mg kg-1 scores 0.16. A pH of 5.0 measured in CaCl2 scores 0.61 against a
water-calibrated curve and 0.92 once converted.

So the unit is treated here as what it is: a fact about the data that only
the person who produced it knows. eSMAF proposes one from the column header,
requires confirmation, converts explicitly, and writes what it did into the
provenance of the result.

One conversion is not a constant. Values reported per volume come from a
scoop of air-dried soil sieved to 2 mm, so the density that puts them on a
mass basis is the density of that loose laboratory sample -- near 1 kg dm-3 --
and *not* the field bulk density, which describes a structure the sieving
destroyed. That density can be assumed to be 1, or read from the site's
texture class; the choice is the user's and travels with the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence

import pandas as pd

from .indicators import BY_KEY, INDICATORS

#: Molar mass divided by charge, for the exchangeable cations a Brazilian
#: report gives in millimoles of charge per cubic decimetre.
EQUIVALENT_MASS = {"K": 39.0983}

#: Van Bemmelen. Organic matter carries roughly 58 % carbon, so dividing by
#: this converts one to the other. It is a convention, not a measurement, and
#: eSMAF says so wherever it uses it.
ORGANIC_MATTER_TO_CARBON = 1.724


@dataclass(frozen=True)
class Unit:
    """One way a measurement can arrive."""

    id: str
    label: str                 # shown in the interface
    note: str = ""             # what it means, and what is done about it
    #: Per volume of *sieved* soil, as a laboratory scoop measures it. The
    #: divisor is the density of that loose sample, near 1 kg dm-3.
    volume_basis: bool = False
    #: Per volume of *intact* soil, as a volumetric ring measures it. The
    #: divisor is the field bulk density of the same sample, which the dataset
    #: may carry in its own column. The two are not interchangeable: sieving
    #: destroys the structure bulk density describes.
    bulk_basis: bool = False
    derived: bool = False      # not the quantity itself (organic matter, pH basis)
    same_number: bool = False  # a different name for the same value

    @property
    def native(self) -> bool:
        return not self.volume_basis and not self.bulk_basis and not self.derived


def _u(id, label, note="", volume_basis=False, derived=False, same_number=False,
       bulk_basis=False):
    return Unit(id, label, note, volume_basis, bulk_basis, derived, same_number)


#: What each indicator may arrive as. The first entry of each list is the unit
#: the eSMAF template asks for and the one SMAF's curve is defined on.
UNITS: dict[str, tuple[Unit, ...]] = {
    "BD": (_u("g/cm3", "g cm-3"),
           _u("kg/dm3", "kg dm-3", "Numerically the same as g cm-3.",
              same_number=True)),
    "AGG": (_u("pct", "%"),
            _u("fraction", "fraction (0-1)", "Multiplied by 100.")),
    "WFPS": (_u("fraction", "fraction (0-1)"),
             _u("pct", "%", "Divided by 100.")),
    "AWC": (_u("g/g", "g H2O g-1 soil (gravimetric)"),
            _u("cm3/cm3", "cm3 cm-3 (volumetric)",
               "Divided by the FIELD bulk density of the same sample, which "
               "the dataset must carry: volumetric water content refers to "
               "the volume of intact soil, not of a sieved scoop.",
               bulk_basis=True)),
    "pH": (_u("water", "pH in water (1:1 or 1:2.5)"),
           _u("cacl2", "pH in CaCl2 0.01 mol L-1",
              "Reads below the water value; an offset is added.", derived=True),
           _u("kcl", "pH in KCl 1 mol L-1",
              "Reads below the water value; an offset is added.", derived=True)),
    "P": (_u("mg/kg", "mg kg-1"),
          _u("mg/dm3", "mg dm-3 (per volume of sieved soil)",
             "Divided by the density of the sieved sample.", volume_basis=True)),
    "K": (_u("mg/kg", "mg kg-1"),
          _u("mg/dm3", "mg dm-3 (per volume of sieved soil)",
             "Divided by the density of the sieved sample.", volume_basis=True),
          _u("mmolc/dm3", "mmolc dm-3 (charge, per volume)",
             "Multiplied by 39.1 to reach mg dm-3, then divided by the "
             "density of the sieved sample.", volume_basis=True, derived=True),
          _u("cmolc/dm3", "cmolc dm-3 (charge, per volume)",
             "Multiplied by 391 to reach mg dm-3, then divided by the "
             "density of the sieved sample.", volume_basis=True, derived=True)),
    "SAR": (_u("ratio", "dimensionless ratio"),),
    "EC": (_u("dS/m", "dS m-1"),
           _u("mS/cm", "mS cm-1", "Numerically the same as dS m-1.",
              same_number=True),
           _u("uS/cm", "uS cm-1", "Divided by 1000.")),
    "SOC": (_u("pct", "organic carbon, %"),
            _u("g/kg", "organic carbon, g kg-1", "Divided by 10."),
            _u("g/dm3", "organic carbon, g dm-3",
               "Divided by the density of the sieved sample, then by 10.",
               volume_basis=True),
            _u("om_pct", "organic MATTER, %",
               "Divided by 1.724 (Van Bemmelen) to estimate carbon.",
               derived=True),
            _u("om_g/kg", "organic MATTER, g kg-1",
               "Divided by 1.724 and by 10.", derived=True),
            _u("om_g/dm3", "organic MATTER, g dm-3",
               "Divided by the density of the sieved sample, by 1.724 and "
               "by 10.", volume_basis=True, derived=True)),
    "PMN": (_u("mg/kg", "mg kg-1"),
            _u("mg/dm3", "mg dm-3", "Divided by the density of the sieved sample.",
               volume_basis=True)),
    "MBC": (_u("mg/kg", "mg kg-1"),
            _u("mg/dm3", "mg dm-3", "Divided by the density of the sieved sample.",
               volume_basis=True)),
    "BG": (_u("mg/kg/h", "mg PNP kg-1 h-1"),
           _u("mg/dm3/h", "mg PNP dm-3 h-1",
              "Divided by the density of the sieved sample.", volume_basis=True),
           _u("umol/g/h", "umol PNP g-1 h-1",
              "Multiplied by 139.11 to reach mg kg-1 h-1.", derived=True)),
}

#: The unit eSMAF's template asks for, per indicator.
DEFAULT_UNIT = {key: options[0].id for key, options in UNITS.items()}


def options(indicator: str) -> tuple[Unit, ...]:
    return UNITS.get(indicator, ())


def get(indicator: str, unit_id: str) -> Unit | None:
    for unit in UNITS.get(indicator, ()):
        if unit.id == unit_id:
            return unit
    return None


def label(indicator: str, unit_id: str) -> str:
    unit = get(indicator, unit_id)
    return unit.label if unit else unit_id


def must_be_declared(indicator: str) -> bool:
    """Does the choice of unit change the number?

    Bulk density in kg dm-3 is bulk density in g cm-3; asking which one it is
    would be bureaucracy. Phosphorus per kilogram and per cubic decimetre are
    different numbers, and that question has to be asked.
    """
    choices = options(indicator)
    return any(not unit.same_number for unit in choices[1:])


def needs_density(declared: Mapping[str, str]) -> list[str]:
    """Indicators declared per volume of sieved soil."""
    return [key for key, unit_id in declared.items()
            if (u := get(key, unit_id)) is not None and u.volume_basis]


def needs_bulk_density(declared: Mapping[str, str]) -> list[str]:
    """Indicators declared per volume of intact soil, which need the BD column."""
    return [key for key, unit_id in declared.items()
            if (u := get(key, unit_id)) is not None and u.bulk_basis]


def is_default(declared: Mapping[str, str]) -> bool:
    return all(unit_id == DEFAULT_UNIT.get(key)
               for key, unit_id in declared.items())


# ------------------------------------------------------------------ headers


#: Fragments that identify a unit in a column header. Longest match wins, so
#: "om_g/dm3" is not mistaken for "g/dm3".
HEADER_HINTS: dict[str, tuple[tuple[str, ...], str]] = {
    "P": ((("mgdm3", "mgdm-3", "mgdm"), "mg/dm3"),
          (("mgkg", "mgkg-1"), "mg/kg")),
    "K": ((("mmolcdm3", "mmolcdm", "mmolc"), "mmolc/dm3"),
          (("cmolcdm3", "cmolcdm", "cmolc"), "cmolc/dm3"),
          (("mgdm3", "mgdm-3", "mgdm"), "mg/dm3"),
          (("mgkg", "mgkg-1"), "mg/kg")),
    "PMN": ((("mgdm3", "mgdm"), "mg/dm3"), (("mgkg",), "mg/kg")),
    "MBC": ((("mgdm3", "mgdm"), "mg/dm3"), (("mgkg",), "mg/kg")),
    "BG": ((("umolgh", "umolg", "umol"), "umol/g/h"),
           (("mgdm3h", "mgdm3", "mgdm"), "mg/dm3/h"),
           (("mgkgh", "mgkg"), "mg/kg/h")),
    # A header of "MO" says the column is organic matter rather than carbon,
    # but not whether it is a percentage or grams per cubic decimetre -- the
    # difference between a score of 1.00 and one of 0.03. So the bare name
    # states nothing here and the interface asks.
    "SOC": ((("mogdm3", "omgdm3", "mogdm", "omgdm", "somgdm3"), "om_g/dm3"),
            (("mogkg", "omgkg", "somgkg"), "om_g/kg"),
            (("mopct", "ompct", "sompct"), "om_pct"),
            (("gdm3", "gdm"), "g/dm3"),
            (("gkg",), "g/kg"),
            (("socpct", "tocpct", "cpct", "percent"), "pct")),
    "pH": ((("cacl2", "cacl"), "cacl2"),
           (("kcl",), "kcl"),
           (("h2o", "water", "agua"), "water")),
    "AWC": ((("cm3cm3", "cm3", "volumetric", "volumetrico"), "cm3/cm3"),
            (("gg", "gravimetric", "gravimetrico", "gh2ogsoil"), "g/g")),
    "WFPS": ((("pct", "percent"), "pct"), (("fraction", "fracao"), "fraction")),
    "AGG": ((("pct", "percent"), "pct"), (("fraction",), "fraction")),
    "EC": ((("uscm", "µscm"), "uS/cm"), (("mscm",), "mS/cm"), (("dsm",), "dS/m")),
    "BD": ((("kgdm3", "kgdm"), "kg/dm3"), (("gcm3", "gcm"), "g/cm3")),
}


def _norm(header: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", str(header))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch.lower() for ch in text if ch.isalnum())


def from_header(indicator: str, header: str) -> str | None:
    """The unit a column header states, or None when it states none.

    Only an explicit statement counts. A column called simply "P" says
    nothing about its unit, and a guess there is exactly the assumption this
    module exists to prevent.
    """
    text = _norm(header)
    for fragments, unit_id in HEADER_HINTS.get(indicator, ()):
        if any(fragment in text for fragment in fragments):
            return unit_id
    return None


def propose(frame_columns: Iterable[str],
            headers: Mapping[str, str] | None = None) -> dict[str, str | None]:
    """A unit per indicator column, read from its header where it says one."""
    headers = headers or {}
    proposed: dict[str, str | None] = {}
    for indicator in INDICATORS:
        if indicator.key not in frame_columns:
            continue
        header = headers.get(indicator.key, indicator.key)
        proposed[indicator.key] = from_header(indicator.key, header)
    return proposed


# --------------------------------------------------------------- presets


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    description: str
    units: dict[str, str]


PRESETS: tuple[Preset, ...] = (
    Preset(
        "esmaf", "eSMAF template",
        "The units the eSMAF spreadsheet asks for, which are the units SMAF's "
        "curves are defined on.",
        dict(DEFAULT_UNIT),
    ),
    Preset(
        "br_routine", "Brazilian routine report (IAC / Boletim 100)",
        "What a commercial or university fertility laboratory in Brazil "
        "reports: nutrients per cubic decimetre of sieved soil, potassium as "
        "charge, organic matter instead of carbon, pH in calcium chloride.",
        {"P": "mg/dm3", "K": "mmolc/dm3", "SOC": "om_g/dm3", "pH": "cacl2",
         "PMN": "mg/dm3", "MBC": "mg/dm3", "BG": "mg/dm3/h", "AWC": "cm3/cm3"},
    ),
    Preset(
        "embrapa", "Mass basis (Embrapa manual)",
        "Nutrients per kilogram, carbon as a percentage, pH in water.",
        {"P": "mg/kg", "K": "mg/kg", "SOC": "pct", "pH": "water",
         "PMN": "mg/kg", "MBC": "mg/kg", "BG": "mg/kg/h", "AWC": "g/g"},
    ),
)


def preset(preset_id: str) -> Preset | None:
    return next((p for p in PRESETS if p.id == preset_id), None)


def matching_preset(declared: Mapping[str, str], keys: Sequence[str],
                    prefer: str | None = None) -> str | None:
    """Which preset, if any, the declared units amount to over ``keys``.

    The preset selector reads its own state back from this rather than
    remembering what was clicked, so it cannot claim a preset that the units no
    longer agree with -- change one dropdown by hand and the selector stops
    naming a laboratory system, which is the honest answer.

    More than one preset can match, because two laboratory systems can agree.
    The eSMAF template and the Embrapa mass basis are the same units seen from
    two directions -- the template was built on SMAF's curves, which are defined
    per kilogram -- so for a dataset with no volumetric column they are
    indistinguishable. ``prefer`` keeps the one the user actually chose, which
    is why picking "Mass basis" used to jump back to "eSMAF template" and look
    like a dead entry.
    """
    keys = [k for k in keys if k in UNITS]
    if not keys or any(k not in declared for k in keys):
        return None
    matches = [c.id for c in PRESETS
               if all(c.units.get(k) == declared[k] for k in keys)]
    if not matches:
        return None
    return prefer if prefer in matches else matches[0]


def equivalent_presets(preset_id: str, keys: Sequence[str]) -> list[str]:
    """Other presets that ask for the same units over ``keys``."""
    chosen = preset(preset_id)
    keys = [k for k in keys if k in UNITS]
    if chosen is None or not keys:
        return []
    return [c.id for c in PRESETS
            if c.id != preset_id
            and all(c.units.get(k) == chosen.units.get(k) for k in keys)]


# ----------------------------------------------------- sieved-sample density


#: How to obtain the density that converts a volume basis to a mass basis.
DENSITY_RULES = {
    "assume_one": (
        "Assume 1.00 kg dm-3",
        "Treats a value per cubic decimetre as if it were per kilogram, which "
        "is what Brazilian practice does implicitly when comparing volumetric "
        "results with mass-based critical levels. Exact only where the sieved "
        "sample happens to weigh 1 kg per dm3."),
    "by_texture": (
        "From the texture class of each site (recommended)",
        "A sieved sample of sand packs more densely than one of clay, so the "
        "density is taken from the texture class already chosen for the site. "
        "The table is part of the calculation model and is recorded with the "
        "result."),
}
DEFAULT_DENSITY_RULE = "by_texture"


def sieved_density(model, rule: str, texture: int | None) -> tuple[float, str]:
    """The density to divide a per-volume value by, and how it was obtained."""
    if rule == "assume_one" or texture is None:
        return 1.0, "assumed 1.00 kg dm-3"
    table = model.tables.get("sieved_density", {}).get("texture", {})
    value = table.get(str(texture))
    if value is None:
        return 1.0, "assumed 1.00 kg dm-3 (no value for this texture class)"
    return float(value), f"{float(value):.2f} kg dm-3, from texture class {texture}"


def ph_offset(model, basis: str) -> float:
    return float(model.tables.get("pH", {}).get("basis_offset", {}).get(basis, 0.0))


# ------------------------------------------------------------- conversion


@dataclass
class Conversion:
    """What was done to one column, in words, for the record."""

    indicator: str
    declared: str
    to: str
    detail: str
    rows: int


def convert(frame: pd.DataFrame, declared: Mapping[str, str], model,
            texture_of_site: Callable[[str], int | None],
            density_rule: str = DEFAULT_DENSITY_RULE
            ) -> tuple[pd.DataFrame, list[Conversion], list[str]]:
    """Put every indicator column on the basis its curve is defined on.

    Returns the converted frame, a record of what was done, and the warnings
    that belong with the result. The input frame is not modified: the values
    the user supplied stay exactly as they supplied them, and the converted
    values are a separate layer, which is what lets a surprising score be
    traced back to the number that produced it.
    """
    out = frame.copy()
    done: list[Conversion] = []
    warnings: list[str] = []

    sites = (out["site"] if "site" in out.columns
             else pd.Series(["" for _ in range(len(out))], index=out.index))
    densities = {}
    for name in sites.unique():
        densities[name] = sieved_density(model, density_rule,
                                         texture_of_site(name))

    bulk = (pd.to_numeric(out["BD"], errors="coerce")
            if "BD" in out.columns else None)

    for key, unit_id in declared.items():
        if key not in out.columns:
            continue
        unit = get(key, unit_id)
        if unit is None or unit.id == DEFAULT_UNIT.get(key):
            continue
        values = pd.to_numeric(out[key], errors="coerce")
        if unit.bulk_basis:
            if bulk is None or not bulk.notna().any():
                warnings.append(
                    f"{BY_KEY[key].label} was supplied per volume of intact "
                    "soil, and converting it to a mass basis needs the field "
                    "bulk density of the same sample, which this dataset does "
                    "not carry. It was left out of the analysis.")
                out[key] = pd.NA
                continue
            density = bulk
        else:
            density = pd.Series([densities[s][0] for s in sites], index=out.index)
        converted, detail = _apply(key, unit.id, values, density, model)
        if converted is None:
            continue
        out[key] = converted
        how = {name: densities[name][1] for name in densities}
        if unit.bulk_basis:
            detail += (" The divisor is the field bulk density of each sample, "
                       "read from the bulk density column.")
        elif unit.volume_basis:
            shown = sorted(set(how.values()))
            detail += " Sieved-sample density: " + "; ".join(shown) + "."
        done.append(Conversion(key, unit.id, DEFAULT_UNIT.get(key, ""), detail,
                               int(values.notna().sum())))

    for record in done:
        warnings.extend(_warn(record))
    return out, done, warnings


def _apply(key: str, unit_id: str, values: pd.Series, density: pd.Series,
           model) -> tuple[pd.Series | None, str]:
    name = BY_KEY[key].label

    if key == "pH":
        offset = ph_offset(model, unit_id)
        basis = label("pH", unit_id)
        return values + offset, (
            f"{name} was supplied as {basis} and {offset:+.2f} was added to "
            "put it on the water basis the scoring curve is defined on.")

    if key == "AGG" and unit_id == "fraction":
        return values * 100.0, f"{name} was supplied as a fraction and multiplied by 100."
    if key == "WFPS" and unit_id == "pct":
        return values.where(values <= 1.0, values / 100.0), (
            f"{name} was supplied as a percentage and divided by 100.")
    if key == "BD" and unit_id == "kg/dm3":
        return values, f"{name} in kg dm-3 is numerically g cm-3; nothing changed."
    if key == "EC":
        if unit_id == "mS/cm":
            return values, f"{name} in mS cm-1 is numerically dS m-1; nothing changed."
        if unit_id == "uS/cm":
            return values / 1000.0, f"{name} was supplied in uS cm-1 and divided by 1000."
    if key == "BG" and unit_id == "umol/g/h":
        return values * 139.11, (
            f"{name} was supplied in umol PNP g-1 h-1 and multiplied by 139.11 "
            "(the molar mass of p-nitrophenol) to reach mg kg-1 h-1.")

    if key == "K" and unit_id in ("mmolc/dm3", "cmolc/dm3"):
        scale = EQUIVALENT_MASS["K"] * (10.0 if unit_id == "cmolc/dm3" else 1.0)
        return values * scale / density, (
            f"{name} was supplied as charge per volume and multiplied by "
            f"{scale:.4g} to reach mg dm-3, then divided by the density of "
            "the sieved sample to reach mg kg-1.")

    if key == "SOC":
        carbon = values
        steps = []
        if unit_id.startswith("om_"):
            carbon = carbon / ORGANIC_MATTER_TO_CARBON
            steps.append(f"divided by {ORGANIC_MATTER_TO_CARBON} (Van Bemmelen) "
                         "to estimate organic carbon from organic matter")
        if unit_id.endswith("g/dm3"):
            carbon = carbon / density
            steps.append("divided by the density of the sieved sample")
        if unit_id.endswith(("g/kg", "g/dm3")):
            carbon = carbon / 10.0
            steps.append("divided by 10 to reach per cent")
        if not steps:
            return None, ""
        return carbon, f"{name} was " + ", then ".join(steps) + "."

    if unit_id == "cm3/cm3":
        return values / density, (
            f"{name} was supplied per volume of intact soil and divided by "
            "the bulk density of the sample to reach a gravimetric basis.")

    if unit_id in ("mg/dm3", "mg/dm3/h"):
        return values / density, (
            f"{name} was supplied per volume of sieved soil and divided by "
            "the density of that sample to reach a mass basis.")

    return None, ""


#: Where a measurement of agricultural topsoil usually falls, in the unit the
#: curve is defined on. Not a validity range -- soils outside these bands
#: exist -- but a net for the one mistake no later check can catch: a column
#: declared in the wrong unit. Values far outside say more about the
#: declaration than about the soil.
TYPICAL: dict[str, tuple[float, float]] = {
    "BD": (0.7, 1.9), "AGG": (3.0, 100.0), "WFPS": (0.05, 0.98),
    "AWC": (0.02, 0.45), "pH": (3.5, 9.0), "P": (0.5, 400.0),
    "K": (5.0, 800.0), "SAR": (0.0, 40.0), "EC": (0.005, 20.0),
    "SOC": (0.1, 15.0), "PMN": (0.5, 120.0), "MBC": (30.0, 3000.0),
    "BG": (5.0, 900.0),
}


def on_curve_basis(indicator: str, values: pd.Series, declared: str | None,
                   model, density: float = 1.0) -> tuple[pd.Series, str]:
    """The values as the scoring curve will receive them, and how they got there.

    A range check has to be made on this, not on the column as supplied.
    Water-filled pore space declared as a percentage is 22 to 59 in the file
    and 0.22 to 0.59 by the time the curve sees it; comparing the supplied
    numbers with the curve's own limits reports an impossible value for a
    column that is perfectly well declared.

    Where the conversion depends on a density, ``density`` stands in for it:
    the sieved-sample table spans 0.95 to 1.25 kg dm-3, which is close enough
    for deciding whether a value is possible and is said in the returned note.
    """
    numeric = pd.to_numeric(values, errors="coerce")
    if not declared or declared == DEFAULT_UNIT.get(indicator):
        return numeric, ""
    unit = get(indicator, declared)
    if unit is None:
        return numeric, ""
    divisor = pd.Series([density] * len(numeric), index=numeric.index)
    converted, _detail = _apply(indicator, declared, numeric, divisor, model)
    if converted is None:
        return numeric, ""
    note = f", reading the column as {label(indicator, declared)}"
    if unit.volume_basis or unit.bulk_basis:
        note += f" with the density taken as {density:.2f} for this check"
    return pd.to_numeric(converted, errors="coerce"), note


def review(indicator: str, values: pd.Series, declared: str, model,
           density: float = 1.0) -> str | None:
    """Does the declared unit put these values where soil values live?

    Answers with the alternative that would, when there is one. This is the
    only check that can catch a declaration that is simply wrong, and the
    case it is built for is real: potassium of 0.2 is an ordinary number in
    mmolc dm-3 and an impossible one in mg kg-1, yet both pass every range
    check, because the range starts at zero.
    """
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty or indicator not in TYPICAL:
        return None
    band = TYPICAL[indicator]
    density_series = pd.Series([density] * len(numeric), index=numeric.index)

    def median_under(unit_id: str) -> float | None:
        if unit_id == DEFAULT_UNIT.get(indicator):
            return float(numeric.median())
        converted, _ = _apply(indicator, unit_id, numeric, density_series, model)
        if converted is None:
            return float(numeric.median())
        converted = converted.dropna()
        return float(converted.median()) if len(converted) else None

    here = median_under(declared)
    if here is None or band[0] <= here <= band[1]:
        return None

    candidates = [u for u in options(indicator) if u.id != declared
                  and (m := median_under(u.id)) is not None
                  and band[0] <= m <= band[1]]
    name = BY_KEY[indicator].label
    message = (
        f"{name} was declared as {label(indicator, declared)}, which puts the "
        f"middle of these values at {here:.4g} {label(indicator, DEFAULT_UNIT[indicator])}. "
        f"Soil normally falls between {band[0]:g} and {band[1]:g}.")
    if candidates:
        shown = " or ".join(label(indicator, u.id) for u in candidates[:2])
        message += f" Values of this size are what {shown} would give."
    return message


def _warn(record: Conversion) -> list[str]:
    """The conversions that deserve to be seen, not merely recorded."""
    if record.indicator == "SOC" and record.declared.startswith("om_"):
        return [
            "Soil organic carbon was estimated from organic matter by dividing "
            f"by {ORGANIC_MATTER_TO_CARBON} (Van Bemmelen). That ratio is a "
            "convention, not a measurement, and it varies between soils; "
            "a measured organic carbon value is preferable wherever one "
            "exists, and the score should be read as resting on the "
            "conversion."]
    if record.indicator == "pH" and record.declared in ("cacl2", "kcl"):
        return [
            f"pH was supplied as {label('pH', record.declared)} and converted "
            "to the water basis the scoring curve is defined on. The offset is "
            "an empirical average and varies with the soil; where a pH "
            "measured in water exists it is the better input."]
    return []
