"""Does the engine reproduce the original SMAF spreadsheet?

The reference file holds the computed values of the example-curve tables in
SMAF-QS_2022.xlsx together with the factor classes each column was built with.
Testing against numbers the spreadsheet itself produced -- rather than against
numbers re-derived from the same equations -- makes this a check on the
implementation and not on the transcription.

Two blocks in the spreadsheet carry defects of their own, and this file deals
with each explicitly rather than quietly working around it:

* SOC and BG example curves. The second term of ``c = c1*c2 + c1*c2*c3`` reads
  ``g(txt)`` from an absolute reference to the first data column instead of
  each column's own texture class. Those columns are marked ``quirk`` in the
  reference file; the test reproduces the quirk to prove the equation itself
  matches, and a separate test asserts that the engine deliberately does not.
* The "Parameter Table in Database" blocks. Those are hand-built exports and
  disagree with the operational formulas for PMN (multiplicative instead of
  additive ``c``) and BD (fine-texture rows computed with the range of the
  very fine class). They are not used as reference data.

Run with:  python -m pytest tests/ -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from esmaf_core import equations as eq
from esmaf_core.crops import get_crop
from esmaf_core.models import load_model
from esmaf_core.parameters import SiteFactors, resolve

REFERENCE = Path(__file__).parent / "reference" / "smaf_qs_2022_curves.json"
TOLERANCE = 1e-3
#: The crop only parameterises pH, EC and P, none of which appear in the
#: example-curve tables, so any database entry serves.
ANY_CROP = "Corn, grain"

_FIELDS = set(SiteFactors.__dataclass_fields__)


def load_cases():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))["cases"]


def _clip(value: float) -> float:
    """SMAF bounds scores to [0, 1]; the example tables print the raw value."""
    return min(1.0, max(0.0, value))


#: Factor classes are mandatory now, so a case that exercises one indicator
#: still has to name the rest. These fillers are never read by the indicator
#: under test; each case overrides the factors that actually shape its curve.
FILLER = {
    "region": 2, "season": 1, "climate": 1, "slope": 1, "texture": 3,
    "mineral": 3, "organic_matter": 3, "iron_oxide": 2, "weathering": 3,
    "p_method": 2, "ec_method": 1,
}


def _resolve(factors: dict):
    selection = dict(FILLER)
    selection.update({k: v for k, v in factors.items() if k in _FIELDS})
    return resolve(load_model("esmaf-2.0"), SiteFactors(**selection),
                   get_crop(ANY_CROP))


def _spreadsheet_c(model_table: dict, factors: dict, quirk_texture: int) -> float:
    """Rebuild ``c`` the way the spreadsheet's own formula does it."""
    c1 = model_table["c_organic_matter"][str(factors["organic_matter"])]
    c2_own = model_table["c_texture"][str(factors["texture"])]
    c2_quirk = model_table["c_texture"][str(quirk_texture)]
    c3 = model_table["c_climate"][str(factors["climate"])]
    return (c1 * c2_own) + (c1 * c2_quirk * c3)


CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c['indicator']}-{c['label']}")
def test_curve_matches_smaf_spreadsheet(case):
    indicator = case["indicator"]
    model = load_model("esmaf-2.0")

    if indicator == "SAR":
        table = model.table("SAR")
        ec = case["factors"]["ec_saturation"]
        for x, expected in case["points"]:
            got = eq.score_sar(x, ec, table).raw
            assert got == pytest.approx(_clip(expected), abs=TOLERANCE), (
                f"SAR at EC={ec}, SAR={x}: engine {got:.5f} vs spreadsheet {expected:.5f}"
            )
        return

    params = _resolve(case["factors"])

    if case.get("quirk") == "fixed_texture_reference":
        table = model.table(indicator)
        c = _spreadsheet_c(table, case["factors"], case["quirk_texture"])
        kwargs = {"a": table["a"], "b": table["b"], "c": c}
        if "divisor" in table:
            kwargs["divisor"] = table["divisor"]
        fn = eq.score_soc if indicator == "SOC" else eq.score_bg
        for x, expected in case["points"]:
            got = fn(x, **kwargs).value
            assert got == pytest.approx(_clip(expected), abs=TOLERANCE), (
                f"{indicator} ({case['label']}) at x={x}, reproducing the "
                f"spreadsheet's fixed texture reference: engine {got:.5f} "
                f"vs spreadsheet {expected:.5f}"
            )
        return

    fn = {
        "AGG": lambda x: eq.score_agg(x, **params["AGG"]),
        "BD": lambda x: eq.score_bd(x, **params["BD"]),
        "SOC": lambda x: eq.score_soc(x, **params["SOC"]),
        "BG": lambda x: eq.score_bg(x, **params["BG"]),
        "PMN": lambda x: eq.score_pmn(x, **params["PMN"]),
        "MBC": lambda x: eq.score_mbc(x, **params["MBC"]),
        "WFPS": lambda x: eq.score_wfps_biological(x, **params["WFPS_BiolAct"]),
        "AWC": lambda x: (eq.score_awc_arid if params["AWC"]["region"] == "arid"
                          else eq.score_awc_humid)(
            x, params["AWC"]["a"], params["AWC"]["b"],
            params["AWC"]["c"], params["AWC"]["d"]),
    }[indicator]

    for x, expected in case["points"]:
        got = fn(x).value
        assert got == pytest.approx(_clip(expected), abs=TOLERANCE), (
            f"{indicator} ({case['label']}) at x={x}: "
            f"engine {got:.5f} vs spreadsheet {expected:.5f}"
        )


def test_engine_uses_each_columns_own_texture_class():
    """The corrected form is what the engine actually computes.

    Guards against someone 'fixing' the engine to match the spreadsheet's
    example table and reintroducing the fixed-reference defect.
    """
    model = load_model("esmaf-2.0")
    table = model.table("SOC")
    factors = {"organic_matter": 2, "texture": 4, "climate": 1}
    params = _resolve(factors)

    c1 = table["c_organic_matter"]["2"]
    c2 = table["c_texture"]["4"]
    c3 = table["c_climate"]["1"]
    assert params["SOC"]["c"] == pytest.approx((c1 * c2) + (c1 * c2 * c3))
    assert params["SOC"]["c"] != pytest.approx(
        _spreadsheet_c(table, factors, quirk_texture=3)
    )


def test_reference_file_is_substantial():
    points = sum(len(c["points"]) for c in CASES)
    indicators = {c["indicator"] for c in CASES}
    assert points >= 500
    assert indicators == {"AGG", "BD", "SOC", "BG", "PMN", "MBC", "WFPS", "AWC", "SAR"}
