"""The range checks belong to the curve, so they run on the curve's basis.

Before this, the analysis check compared a column with the limits of the
scoring curve while the column was still in the unit the laboratory reported.
A water-filled pore space column declared as a percentage -- correctly, and
with the conversion already arranged -- therefore produced "36 values fall
outside the possible range 0 to 1" and blocked the analysis. The reference
dataset shipped with the application is one such file.

What must not be lost in fixing it is the opposite case: the same column
declared as a fraction really is impossible, and must still be refused.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from esmaf_core import importer, units as un, validation
from esmaf_core.models import load_model
from esmaf_core.parameters import SiteFactors
from esmaf_core.weights import WeightConfig

REFERENCE = Path(__file__).parent / "reference"

FACTORS = SiteFactors(region=2, season=1, climate=1, slope=2, texture=4,
                      mineral=3, organic_matter=3, iron_oxide=2,
                      weathering=2, p_method=5, ec_method=1)


@pytest.fixture(scope="module")
def model():
    return load_model("esmaf-2.0")


def _check(frame, declared):
    return validation.check(frame, FACTORS.as_dict(), WeightConfig(),
                            "esmaf-2.0", units=declared)


def _frame(**columns):
    base = {"land_use": ["Cropland"], "management": ["NT"],
            "crop": ["Corn, grain"], "depth": ["0-20"]}
    length = max(len(v) for v in columns.values()) if columns else 1
    for key, value in base.items():
        base[key] = value * length
    base.update(columns)
    return pd.DataFrame(base)


# ---------------------------------------------------------- the helper itself

def test_curve_basis_converts_a_percentage(model):
    values, note = un.on_curve_basis("WFPS", pd.Series([22.2, 58.7]), "pct", model)
    assert values.tolist() == pytest.approx([0.222, 0.587])
    assert "%" in note


def test_curve_basis_leaves_the_engine_unit_alone(model):
    values, note = un.on_curve_basis("WFPS", pd.Series([0.42]), "fraction", model)
    assert values.tolist() == pytest.approx([0.42])
    assert note == ""


def test_curve_basis_says_when_it_assumed_a_density(model):
    values, note = un.on_curve_basis("K", pd.Series([0.2]), "mmolc/dm3", model)
    assert values.iloc[0] == pytest.approx(7.82, abs=0.01)
    assert "density" in note


def test_curve_basis_handles_an_unknown_declaration(model):
    values, note = un.on_curve_basis("P", pd.Series([12.0]), "not-a-unit", model)
    assert values.tolist() == [12.0]
    assert note == ""


def test_curve_basis_handles_no_declaration(model):
    values, note = un.on_curve_basis("P", pd.Series([12.0]), None, model)
    assert values.tolist() == [12.0]
    assert note == ""


# ------------------------------------------------------------- the check path

def test_percentage_wfps_is_accepted():
    report = _check(_frame(WFPS=[22.2, 41.0, 58.7]), {"WFPS": "pct"})
    assert not [f for f in report.errors if f.scope == "WFPS"]


def test_percentage_wfps_declared_as_a_fraction_is_refused():
    report = _check(_frame(WFPS=[22.2, 41.0, 58.7]), {"WFPS": "fraction"})
    assert [f for f in report.errors if f.scope == "WFPS"]


def test_organic_carbon_in_grams_per_kilogram_is_accepted():
    report = _check(_frame(SOC=[21.0, 36.7]), {"SOC": "g/kg"})
    assert not [f for f in report.errors if f.scope == "SOC"]


def test_organic_matter_per_volume_is_accepted():
    """3.7 g dm-3 of organic matter is 0.21 % carbon, which is a real soil."""
    report = _check(_frame(SOC=[3.7]), {"SOC": "om_g/dm3"})
    assert not [f for f in report.errors if f.scope == "SOC"]


def test_potassium_as_charge_is_accepted():
    report = _check(_frame(K=[0.2, 1.5, 3.0]), {"K": "mmolc/dm3"})
    assert not [f for f in report.errors if f.scope == "K"]


def test_aggregate_stability_as_a_fraction_is_accepted():
    report = _check(_frame(AGG=[0.62, 0.93]), {"AGG": "fraction"})
    assert not [f for f in report.errors if f.scope == "AGG"]


def test_the_message_names_the_basis_it_checked():
    report = _check(_frame(WFPS=[4200.0]), {"WFPS": "pct"})
    found = [f for f in report.errors if f.scope == "WFPS"]
    assert found
    assert "reading the column as" in found[0].what


def test_non_numeric_values_are_still_reported():
    report = _check(_frame(WFPS=["n.a.", 41.0]), {"WFPS": "pct"})
    assert [f for f in report.errors if f.scope == "WFPS" and "numeric" in f.what]


# ------------------------------------------------------ the reference dataset

def test_the_reference_dataset_can_be_analysed():
    """demo_dataset.xlsx reports WFPS as a percentage, as many files do."""
    path = REFERENCE / "demo_dataset.xlsx"
    if not path.exists():
        pytest.skip("reference dataset not available")
    report_in = importer.load(path)
    declared = {m.target: m.unit for m in report_in.mappings
                if m.target and m.unit}
    declared.update({"pH": "water", "BG": "mg/kg/h"})
    report = _check(report_in.frame, declared)
    assert report.can_run, [f.one_line() for f in report.errors]
