"""Crop parameter database.

Three indicators -- pH, EC and P -- are scored against crop-specific optima.
The database is a CSV so that adding a crop is a data edit, not a code
change, and so that a project can record exactly which version it used.
"""

from __future__ import annotations

import csv
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "data" / "crops.csv"

#: Short forms and Portuguese names that appear in real spreadsheets, mapped to
#: the entry they mean. The eSMAF template itself ships "BCerrado", which the
#: web version could not resolve; these are the names people actually type, not
#: guesses. A name that is merely similar is still never substituted silently --
#: see get_crop.
ALIASES: dict[str, str] = {
    # Brazilian native vegetation
    "bcerrado": "Brazilian cerrado",
    "cerrado": "Brazilian cerrado",
    "bmata": "Brazilian atlantic forest",
    "bmataatlantica": "Brazilian atlantic forest",
    "mataatlantica": "Brazilian atlantic forest",
    "atlanticforest": "Brazilian atlantic forest",
    "bfloresta": "Brazilian atlantic forest",
    "bcaatinga": "Brazilian caatinga",
    "caatinga": "Brazilian caatinga",
    "manguezal": "Mangrove",
    "mangue": "Mangrove",
    # Brazilian crops and pasture
    "bbrachiaria": "Brazilian brachiaria",
    "brachiaria": "Brazilian brachiaria",
    "braquiaria": "Brazilian brachiaria",
    "bbraquiaria": "Brazilian brachiaria",
    "pastagem": "Brazilian brachiaria",
    "bcana": "Brazilian sugarcane",
    "bsugarcane": "Brazilian sugarcane",
    "bcanadeacucar": "Brazilian sugarcane",
    "canadeacucar": "Brazilian sugarcane",
    "cana": "Brazilian sugarcane",
    "eucalipto": "Eucalyptus",
    "beucalipto": "Eucalyptus",
    "soja1": "Soybean I",
    "soja2": "Soybean II",
    "soja3": "Soybean III",
    "soja4": "Soybean IV",
    "sojai": "Soybean I",
    "sojaii": "Soybean II",
    "sojaiii": "Soybean III",
    "sojaiv": "Soybean IV",
    # common English shorthands
    "maize": "Corn, grain",
    "corn": "Corn, grain",
    "milho": "Corn, grain",
    "wheat": "Wheat, spring",
    "trigo": "Wheat, spring",
    "algodao": "Cotton",
    "arroz": "Rice",
    "cafe": "Coffee",
    "feijao": "Beans",
}


@dataclass(frozen=True)
class Crop:
    name: str
    scientific_name: str
    code: int
    ec_threshold_saturation: float   # T, dS/m on a saturation paste
    ec_threshold_sand: float
    ec_decline_rate: float           # dT, % yield loss per dS/m above T
    ec_slope: float
    ph_max: float
    ph_optimum: float                # b of the Gaussian
    ph_range: float                  # c of the Gaussian
    ph_alt_range: float
    p_optimum: float
    p_max: float                     # crop maximum, mg/kg
    p_crop_factor: float             # b1 of the sufficiency limb
    #: Thirteen entries reach eSMAF with no salinity threshold at all, among
    #: them every Brazilian one and Soybean I to IV. The web version scored
    #: their EC as a flat 1.00, which is a number the database cannot support.
    #: Here the indicator is left out instead -- and if the appropriate
    #: threshold is that of another entry (Soybean I to IV are the same species
    #: as Soybean, differing only in phosphorus response), that can be stated
    #: in the EC_FROM column of crops.csv. Doing it there rather than in code
    #: keeps the decision visible, versioned with the database and reported in
    #: the provenance of every analysis that relied on it.
    ec_from: str = ""                # entry these EC parameters were taken from

    @property
    def has_salinity_threshold(self) -> bool:
        return self.ec_threshold_saturation > 0

    @property
    def display(self) -> str:
        if self.scientific_name and self.scientific_name.strip():
            return f"{self.name} ({self.scientific_name})"
        return self.name


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch.lower() for ch in text if ch.isalnum())


def _f(row: dict, key: str, default: float = 0.0) -> float:
    value = row.get(key, "")
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


@lru_cache(maxsize=1)
def load_crops() -> tuple[Crop, ...]:
    return _resolve_borrowed(_read_crops())


def _resolve_borrowed(crops: tuple[Crop, ...]) -> tuple[Crop, ...]:
    """Apply any EC_FROM instruction in the database.

    One level only, and only onto an entry that has no threshold of its own,
    so the column cannot quietly override a real measurement or chain into a
    loop. An EC_FROM that names something unknown is ignored rather than
    guessed at; the analysis then simply reports no EC score, as before.
    """
    from dataclasses import replace

    by_name = {_norm(c.name): c for c in crops}
    resolved = []
    for crop in crops:
        source = by_name.get(_norm(crop.ec_from)) if crop.ec_from else None
        if (source is not None and source.name != crop.name
                and not crop.has_salinity_threshold
                and source.has_salinity_threshold):
            crop = replace(
                crop,
                ec_threshold_saturation=source.ec_threshold_saturation,
                ec_threshold_sand=source.ec_threshold_sand,
                ec_decline_rate=source.ec_decline_rate,
                ec_slope=source.ec_slope,
                ec_from=source.name,
            )
        else:
            crop = replace(crop, ec_from="")
        resolved.append(crop)
    return tuple(resolved)


def _read_crops() -> tuple[Crop, ...]:
    crops: list[Crop] = []
    with DATA_FILE.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("CROP") or "").strip()
            if not name:
                continue
            crops.append(
                Crop(
                    name=name,
                    scientific_name=(row.get("SCIENTIFIC NAME") or "").strip(),
                    code=int(_f(row, "CODE")),
                    ec_threshold_saturation=_f(row, "EC_1:1_Tsat"),
                    ec_threshold_sand=_f(row, "EC_1:1_Tsand"),
                    ec_decline_rate=_f(row, "EC_1:1_dT"),
                    ec_slope=_f(row, "EC_1:1_m"),
                    ph_max=_f(row, "PH_2:1_max"),
                    ph_optimum=_f(row, "PH_2:1_b"),
                    ph_range=_f(row, "PH_2:1_c"),
                    ph_alt_range=_f(row, "PH_2:1_altc"),
                    p_optimum=_f(row, "Soil_P_opt"),
                    p_max=_f(row, "Soil_P_max"),
                    p_crop_factor=_f(row, "Soil_P_fcrop"),
                    ec_from=(row.get("EC_FROM") or "").strip(),
                )
            )
    return tuple(crops)


@lru_cache(maxsize=1)
def _index() -> dict[str, Crop]:
    index = {_norm(c.name): c for c in load_crops()}
    for alias, target in ALIASES.items():
        crop = index.get(_norm(target))
        if crop is not None:
            index.setdefault(_norm(alias), crop)
    return index


def crop_names() -> list[str]:
    return [c.name for c in load_crops()]


def get_crop(name: str) -> Crop:
    """Look up a crop, tolerating case, accents and spacing but nothing else.

    A crop that is merely *similar* is never substituted silently: choosing
    the wrong curve is a scientific decision, so an unknown name raises with
    the closest candidates attached for the interface to offer.
    """
    crop = _index().get(_norm(name))
    if crop is not None:
        return crop
    raise UnknownCrop(name, suggest_crops(name))


def find_crop(name: str) -> Crop | None:
    return _index().get(_norm(name))


def suggest_crops(name: str, limit: int = 5) -> list[str]:
    import difflib

    keys = list(_index())
    matches = difflib.get_close_matches(_norm(name), keys, n=limit, cutoff=0.5)
    return [_index()[m].name for m in matches]


class UnknownCrop(KeyError):
    def __init__(self, name: str, suggestions: list[str]):
        self.name = name
        self.suggestions = suggestions
        hint = ""
        if suggestions:
            hint = " Did you mean: " + ", ".join(suggestions) + "?"
        super().__init__(
            f"'{name}' is not in the crop database, so the pH, EC and P curves "
            f"cannot be parameterised for it.{hint}"
        )
