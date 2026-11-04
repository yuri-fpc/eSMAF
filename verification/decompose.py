"""Where the eSMAF and the published scores differ, and why.

Every residual in the comparison with Cherubin et al. (2016) is traced to one
identifiable choice made before the arithmetic starts: the basis the pH values
are read on, the texture class of the clayey soils, and two parameter values
that the reference workbook has revised since the study was published.

The "matched" run uses the same equations from :mod:`esmaf_core.equations`
with the parameter values in force when the study was made.  No equation
changes between runs.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "app" / "src"))
sys.path.insert(0, str(HERE))

import cherubin2016 as C  # noqa: E402
from esmaf_core import equations as eq  # noqa: E402
from esmaf_core.models import load_model  # noqa: E402
from run_verification import Config, paired, score  # noqa: E402

MODEL = load_model("esmaf-2.0")

# --- parameter values in force when the study was made ---------------------
# Recorded in the change log of the reference workbook (SMAF-QS):
#   8 July 2015   resin method factor for highly weathered soils: 3.1 -> 1.25
#   31 July 2019  critical P limit for sugarcane: 16 -> 40 mg kg-1
#   31 July 2019 / 28 January 2020  exchangeable K curve recalibrated for
#                 Brazilian response classes
RESIN_2016 = 1.25
CROP_P_OPT_2016 = {"Brazilian cerrado": 6, "Brazilian atlantic forest": 12,
                   "Brazilian brachiaria": 13, "Brazilian sugarcane": 16}
K_COARSE = (1.0541326, -0.009812698)     # SMAF coarse-texture parameters


def texture_of(site: str, land_use: str) -> int:
    return 2 if (site == "Lat_21S" or (site == "Lat_17S" and land_use == "PA")) else 4


def p_crop_b(p_opt: float) -> float:
    """b1 = a' + b' Popt + c' Popt^2, with the workbook's coefficients."""
    return 213.96744 - 39.579185 * p_opt + 2.302051 * p_opt * p_opt


def p_2016(value: float, crop: str, texture: int) -> float:
    t = MODEL.table("P")
    p_opt = CROP_P_OPT_2016[crop]
    result = eq.score_p(
        value, RESIN_2016, p_opt + 6, p_crop_b(p_opt),
        t["sufficiency"], t["environmental"],
        t["b_organic_matter"]["4"], t["b_texture"][str(texture)],
        t["c_organic_matter"]["4"], t["c_texture"][str(texture)],
        t["slope_threshold"]["2"], t["slope_factor"]["2"],
    )
    return round(min(max(result.raw, 0.0), 1.0), 2)


def k_2016(value: float) -> float:
    a, b = K_COARSE
    return round(min(max(a * (1.0 - math.exp(b * value)), 0.0), 1.0), 2)


def table() -> pd.DataFrame:
    """One row per indicator: agreement as run, and after matching the choice."""
    as_stated = paired(score(Config(ph_basis="as_printed", texture_clayey=4,
                                    crop_23S_NV="Brazilian cerrado",
                                    weathering=2)))
    converted = paired(score(Config(ph_basis="ciprandi", texture_clayey=4,
                                    crop_23S_NV="Brazilian cerrado",
                                    weathering=2)))
    very_fine = paired(score(Config(ph_basis="as_printed", texture_clayey=5,
                                    crop_23S_NV="Brazilian cerrado",
                                    weathering=2)))

    def mad(pairs: pd.DataFrame, indicator: str) -> float:
        return pairs[pairs["indicator"] == indicator]["absolute"].mean()

    # P and K recomputed with the 2016 parameter values
    p_dev, k_dev = [], []
    for (site, use, depth), values in C.MEASURED.items():
        texture = texture_of(site, use)
        crop = C.CROP[(site, use)]
        if (site, use) == ("Lat_23S", "NV"):
            crop = "Brazilian cerrado"
        published = C.PUBLISHED[(site, use, depth)]
        p_dev.append(abs(p_2016(values[1], crop, texture) - published[1]))
        k_dev.append(abs(k_2016(values[2]) - published[2]))

    rows = [
        {"indicator": "pH", "as_run": mad(as_stated, "pH"),
         "matched": mad(as_stated, "pH"),
         "alternative": mad(converted, "pH"),
         "choice": "pH read on the basis the curve is defined on",
         "alternative_label": "converted with Ciprandi (1993) first"},
        {"indicator": "BD", "as_run": mad(as_stated, "BD"),
         "matched": mad(very_fine, "BD"),
         "alternative": mad(as_stated, "BD"),
         "choice": "clayey soils in the very fine texture class",
         "alternative_label": "fine texture class"},
        {"indicator": "P", "as_run": mad(as_stated, "P"),
         "matched": float(pd.Series(p_dev).mean()),
         "alternative": mad(as_stated, "P"),
         "choice": "resin factor 1.25 and sugarcane limit 16 mg kg-1",
         "alternative_label": "current parameter set"},
        {"indicator": "K", "as_run": mad(as_stated, "K"),
         "matched": float(pd.Series(k_dev).mean()),
         "alternative": mad(as_stated, "K"),
         "choice": "SMAF coarse-texture K curve",
         "alternative_label": "recalibrated Brazilian K curve"},
        {"indicator": "AGG", "as_run": mad(as_stated, "AGG"),
         "matched": mad(as_stated, "AGG"), "alternative": None,
         "choice": "", "alternative_label": ""},
        {"indicator": "SOC", "as_run": mad(as_stated, "SOC"),
         "matched": mad(as_stated, "SOC"), "alternative": None,
         "choice": "", "alternative_label": ""},
        {"indicator": "MBC", "as_run": mad(as_stated, "MBC"),
         "matched": mad(as_stated, "MBC"), "alternative": None,
         "choice": "", "alternative_label": ""},
        {"indicator": "BG", "as_run": mad(as_stated, "BG"),
         "matched": mad(as_stated, "BG"), "alternative": None,
         "choice": "", "alternative_label": ""},
    ]
    return pd.DataFrame(rows)


def matched_pairs() -> pd.DataFrame:
    """All 180 pairs with every documented choice matched to the study."""
    base = paired(score(Config(ph_basis="as_printed", texture_clayey=4,
                               crop_23S_NV="Brazilian cerrado",
                               weathering=2)))
    out = base.copy()
    for i, row in out.iterrows():
        key = (row["site"], row["land_use"], row["depth"])
        values = C.MEASURED[key]
        if row["indicator"] == "P":
            texture = texture_of(row["site"], row["land_use"])
            out.at[i, "esmaf"] = p_2016(values[1], row["crop"], texture)
        elif row["indicator"] == "K":
            out.at[i, "esmaf"] = k_2016(values[2])
    out["deviation"] = (out["esmaf"] - out["published"]).round(2)
    out["absolute"] = out["deviation"].abs()
    return out


def main() -> None:
    summary = table()
    summary.to_csv(HERE / "decomposition.csv", index=False)
    print(summary.to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    matched = matched_pairs()
    matched.to_csv(HERE / "pairs_matched.csv", index=False)
    print(f"\nevery choice matched: {len(matched)} pairs, "
          f"MAD {matched['absolute'].mean():.3f}, "
          f"within 0.05 {(matched['absolute'] <= 0.05).mean() * 100:.0f} %, "
          f"within 0.10 {(matched['absolute'] <= 0.10).mean() * 100:.0f} %, "
          f"max {matched['absolute'].max():.2f}")
    print("\nby indicator:")
    print(matched.groupby("indicator")["absolute"]
          .agg(["count", "mean", "max"]).round(3).to_string())


if __name__ == "__main__":
    main()
