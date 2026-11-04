"""Assert every number quoted in the version 6 text against the result files.

    python paper/verification/check_numbers.py

Exits non-zero if any number quoted in the article no longer holds.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "app" / "src"))
sys.path.insert(0, str(HERE))

import cherubin2016 as C  # noqa: E402
from run_verification import Config, paired, score  # noqa: E402

primary = pd.read_csv(HERE / "pairs_primary.csv")
matched = pd.read_csv(HERE / "pairs_matched.csv")

CHECKS: list[tuple[str, object, object]] = []


def ck(label: str, got, want) -> None:
    CHECKS.append((label, got, want))


def mad(frame: pd.DataFrame, indicator: str | None = None) -> float:
    part = frame if indicator is None else frame[frame.indicator == indicator]
    return round(part.absolute.mean(), 3)


def within(frame: pd.DataFrame, tolerance: float,
           indicator: str | None = None) -> int:
    part = frame if indicator is None else frame[frame.indicator == indicator]
    return round((part.absolute <= tolerance).mean() * 100)


# ----------------------------------------------------- scope of the comparison
ck("paired scores", len(primary), 180)
ck("site x land use x depth", primary.groupby(["site", "land_use", "depth"]).ngroups, 27)
ck("n per indicator, pH", len(primary[primary.indicator == "pH"]), 27)
ck("n per indicator, MBC", len(primary[primary.indicator == "MBC"]), 9)

cases = json.loads((ROOT / "app" / "tests" / "reference"
                    / "smaf_qs_2022_curves.json").read_text())["cases"]
ck("reference curve values", sum(len(c["points"]) for c in cases), 531)

# --------------------------------------------------------------- primary run
ck("all MAD", mad(primary), 0.067)
ck("all within 0.10 (%)", within(primary, 0.10), 76)
for indicator, want in (("AGG", 0.001), ("SOC", 0.005), ("MBC", 0.009),
                        ("BG", 0.009), ("pH", 0.029), ("BD", 0.068)):
    ck(f"{indicator} MAD", mad(primary, indicator), want)
ck("P mean deviation", round(primary[primary.indicator == "P"].deviation.mean(), 3), 0.159)
ck("K mean deviation", round(primary[primary.indicator == "K"].deviation.mean(), 3), 0.178)

five = primary[primary.indicator.isin(["AGG", "SOC", "MBC", "BG", "pH"])]
ck("five indicators outside 0.10", len(five[five.absolute > 0.10]), 3)
outliers = primary[(primary.indicator == "pH") & (primary.absolute > 0.10)]
ck("pH outliers are Lat_23S sugarcane",
   bool(all((outliers.site == "Lat_23S") & (outliers.land_use == "SC"))), True)
ck("pH outlier deviation", round(outliers.deviation.max(), 2), 0.11)

agg = primary[primary.indicator == "AGG"]
ck("AGS, eSMAF at the maximum", int((agg.esmaf == 1.0).sum()), 27)
ck("AGS, published at the maximum", int((agg.published == 1.0).sum()), 24)

bulk = primary[primary.indicator == "BD"].copy()
bulk["texture"] = [2 if (r.site == "Lat_21S"
                         or (r.site == "Lat_17S" and r.land_use == "PA")) else 4
                   for r in bulk.itertuples()]
ck("BD medium-textured, n", len(bulk[bulk.texture == 2]), 12)
ck("BD medium-textured, MAD", round(bulk[bulk.texture == 2].absolute.mean(), 3), 0.014)
ck("BD medium-textured, max", round(bulk[bulk.texture == 2].absolute.max(), 2), 0.04)
ck("BD fine-textured, n", len(bulk[bulk.texture == 4]), 15)
ck("BD fine-textured, mean deviation", round(bulk[bulk.texture == 4].deviation.mean(), 2), 0.11)

# --------------------------------------------- structure of the P and K residuals
phosphorus = primary[primary.indicator == "P"].groupby("land_use").deviation.mean()
ck("P deviation, native vegetation", round(phosphorus["NV"], 3), 0.093)
ck("P deviation, pasture", round(phosphorus["PA"], 3), 0.327)
ck("P deviation, sugarcane", round(phosphorus["SC"], 3), 0.058)
potassium = primary[primary.indicator == "K"].groupby("land_use").deviation.mean()
ck("K deviation, lowest land use", round(potassium.min(), 3), 0.150)
ck("K deviation, highest land use", round(potassium.max(), 3), 0.198)

# the method factor of the source study, on its own
resin = paired(score(Config(weathering=3)))
resin_p = resin[resin.indicator == "P"]
shift = (primary[primary.indicator == "P"]
         .merge(resin_p, on=["site", "land_use", "depth"], suffixes=("_a", "_b")))
shift["moved"] = shift.esmaf_a - shift.esmaf_b
ck("resin factor, pasture displacement",
   round(shift[shift.land_use == "PA"].moved.mean(), 2), 0.31)
uncropped = resin_p[resin_p.land_use.isin(["NV", "PA"])]
ck("resin factor, NV + PA n", len(uncropped), 18)
ck("resin factor, NV + PA MAD", round(uncropped.absolute.mean(), 3), 0.012)
ck("resin factor, NV + PA max", round(uncropped.absolute.max(), 2), 0.05)

# the coarse-texture potassium curve
K_COARSE = (1.0541326, -0.009812698)
deviations = []
for (site, use, depth), values in C.MEASURED.items():
    a, b = K_COARSE
    got = round(min(max(a * (1.0 - math.exp(b * values[2])), 0.0), 1.0), 2)
    deviations.append(abs(round(got - C.PUBLISHED[(site, use, depth)][2], 2)))
ck("K, coarse-texture curve MAD", round(pd.Series(deviations).mean(), 3), 0.060)

# ---------------------------------------------------------------- matched run
ck("P matched MAD", mad(matched, "P"), 0.021)
ck("P matched within 0.05 (%)", within(matched, 0.05, "P"), 93)
ck("K matched MAD", mad(matched, "K"), 0.060)
ck("all matched MAD", mad(matched), 0.029)
ck("all matched within 0.10 (%)", within(matched, 0.10), 90)
changed = {i for i in matched.indicator.unique()
           if not matched[matched.indicator == i].esmaf.equals(
               primary[primary.indicator == i].esmaf)}
ck("indicators that differ between the runs", sorted(changed), ["K", "P"])

# --------------------------------------------------------------------- report
failures = [c for c in CHECKS if c[1] != c[2]]
for label, got, want in CHECKS:
    mark = "ok  " if got == want else "FAIL"
    print(f"{mark} {label:38s} got {got}   want {want}")
print()
print(f"ALL {len(CHECKS)} CHECKS PASS" if not failures
      else f"{len(failures)} FAILURES")
sys.exit(1 if failures else 0)
