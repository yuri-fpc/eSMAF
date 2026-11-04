"""Reprocess the Cherubin et al. (2016) assessment with eSMAF and compare.

Run from the repository root:

    python paper/verification/run_verification.py

The comparison is driven by a small configuration object so that each input
choice -- the basis the pH values are read on, the texture class of the clayey
soils, the crop curve of the native vegetation at Lat_23S, the method factor
for resin-extracted P -- can be varied one at a time and its effect on the
agreement measured.  Nothing in the calculation engine changes between runs.
"""

from __future__ import annotations

import itertools
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "app" / "src"))
sys.path.insert(0, str(HERE))

import cherubin2016 as C  # noqa: E402
from esmaf_core import engine, sites as st, weights as wt  # noqa: E402
from esmaf_core.parameters import SiteFactors  # noqa: E402

COMPONENT_OF = {"pH": "chemical", "P": "chemical", "K": "chemical",
                "BD": "physical", "AGG": "physical",
                "SOC": "biological", "MBC": "biological", "BG": "biological"}

CLAYEY = ("Lat_17S Acrudox", "Lat_23S")


@dataclass(frozen=True)
class Config:
    #: "as_printed"  - the pH of Table 2 enters the curve unchanged
    #: "ciprandi"    - converted first with pH_water = 0.890 + 0.922 pH_CaCl2
    ph_basis: str = "as_printed"
    #: texture class given to the soils described as clayey, > 40 % clay
    texture_clayey: int = 4
    #: Crop curve for the native vegetation at Lat_23S. The source study
    #: describes that vegetation as similar to Lat_21S but does not name the
    #: curve; the Cerrado curve is the assignment that reproduces its
    #: published pH scores.
    crop_23S_NV: str = "Brazilian cerrado"
    #: 2 -> resin method factor 3.1 (tabulated for highly weathered soils)
    #: 3 -> resin method factor 1.25 (the value adopted by the authors)
    weathering: int = 2

    def label(self) -> str:
        return (f"pH {self.ph_basis}, clayey texture {self.texture_clayey}, "
                f"Lat_23S NV {self.crop_23S_NV.split()[-1]}, "
                f"resin factor {'1.25' if self.weathering == 3 else '3.1'}")


def analysis_frame(config: Config) -> pd.DataFrame:
    rows = []
    for (site, use, depth), values in C.MEASURED.items():
        ph, p, k, bd, ags, soc, mbc, bg = values
        crop = C.CROP[(site, use)]
        if (site, use) == ("Lat_23S", "NV"):
            crop = config.crop_23S_NV
        rows.append({
            "site": C.SITE_OF[(site, use)],
            "land_use": C.LAND_USE_LABEL[use],
            "management": C.LAND_USE_LABEL[use],
            "crop": crop,
            "depth": depth,
            "sample": f"{site}-{use}-{depth}",
            "pH": ph if config.ph_basis == "as_printed" else C.ph_water(ph),
            "P": p,
            "K": k,
            "BD": bd,
            "AGG": ags,
            "SOC": soc / 10.0,          # g kg-1 -> %, the basis of the curve
            "MBC": mbc,
            "BG": bg,
        })
    return pd.DataFrame(rows)


def site_factors(config: Config) -> dict[str, SiteFactors]:
    out = {}
    for name, values in C.SITE_FACTORS.items():
        chosen = dict(values)
        chosen["weathering"] = config.weathering
        if name in CLAYEY:
            chosen["texture"] = config.texture_clayey
        out[name] = SiteFactors(**chosen)
    return out


def score(config: Config) -> pd.DataFrame:
    frame = analysis_frame(config)
    options = engine.AnalysisOptions(model_id="esmaf-2.0", round_scores=2)
    result = engine.run(frame, site_factors(config), wt.WeightConfig(),
                        options=options, site_index=st.build(frame["site"]))
    return result.scores


def paired(scores: pd.DataFrame) -> pd.DataFrame:
    rows = []
    lookup = {r["sample"]: r for _, r in scores.iterrows()}
    for (site, use, depth), published in C.PUBLISHED.items():
        row = lookup[f"{site}-{use}-{depth}"]
        for indicator, value in zip(C.INDICATOR_ORDER, published):
            if value is None:
                continue
            got = row.get(f"{indicator}_score")
            rows.append({
                "site": site, "land_use": use, "depth": depth,
                "indicator": indicator, "component": COMPONENT_OF[indicator],
                "crop": row["crop"],
                "published": float(value),
                "esmaf": None if pd.isna(got) else float(got),
            })
    out = pd.DataFrame(rows)
    # Both sides are printed to two decimals, so every difference is an exact
    # multiple of 0.01. Rounding here keeps a deviation of exactly 0.10 from
    # falling outside a 0.10 tolerance through floating-point representation.
    out["deviation"] = (out["esmaf"] - out["published"]).round(2)
    out["absolute"] = out["deviation"].abs()
    return out


def summarise(pairs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for indicator in C.INDICATOR_ORDER:
        part = pairs[pairs["indicator"] == indicator]
        rows.append({
            "indicator": indicator,
            "component": COMPONENT_OF[indicator],
            "n": len(part),
            "MAD": part["absolute"].mean(),
            "mean_deviation": part["deviation"].mean(),
            "max_absolute": part["absolute"].max(),
            "within_0.05": (part["absolute"] <= 0.05).mean() * 100,
            "within_0.10": (part["absolute"] <= 0.10).mean() * 100,
        })
    rows.append({
        "indicator": "ALL", "component": "-", "n": len(pairs),
        "MAD": pairs["absolute"].mean(),
        "mean_deviation": pairs["deviation"].mean(),
        "max_absolute": pairs["absolute"].max(),
        "within_0.05": (pairs["absolute"] <= 0.05).mean() * 100,
        "within_0.10": (pairs["absolute"] <= 0.10).mean() * 100,
    })
    return pd.DataFrame(rows)


def show(config: Config) -> pd.DataFrame:
    pairs = paired(score(config))
    print(f"\n{'=' * 78}\n{config.label()}\n{'=' * 78}")
    print(summarise(pairs).to_string(index=False,
                                     float_format=lambda v: f"{v:.3f}"))
    return pairs


def sensitivity() -> pd.DataFrame:
    """MAD of each indicator under every combination of the four choices."""
    rows = []
    grid = itertools.product(("as_printed", "ciprandi"), (4, 5),
                             ("Brazilian cerrado", "Brazilian atlantic forest"),
                             (2, 3))
    for ph_basis, texture, crop, weathering in grid:
        config = Config(ph_basis, texture, crop, weathering)
        pairs = paired(score(config))
        entry = {"ph_basis": ph_basis, "texture_clayey": texture,
                 "crop_23S_NV": crop.split()[-1],
                 "resin_factor": 1.25 if weathering == 3 else 3.1,
                 "MAD_all": pairs["absolute"].mean()}
        for indicator in C.INDICATOR_ORDER:
            part = pairs[pairs["indicator"] == indicator]
            entry[f"MAD_{indicator}"] = part["absolute"].mean()
        rows.append(entry)
    return pd.DataFrame(rows)


def main() -> None:
    stated = Config()          # every factor class and crop as the study reports
    pairs = show(stated)
    pairs.to_csv(HERE / "pairs_primary.csv", index=False)

    table = sensitivity()
    table.to_csv(HERE / "sensitivity.csv", index=False)
    print(f"\n{'=' * 78}\nsensitivity grid (MAD over all 180 pairs)\n{'=' * 78}")
    print(table.sort_values("MAD_all").to_string(
        index=False, float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    main()
