"""The unit a measurement arrived in, and what it takes to score it.

The worked example throughout is a real report: laudo 2824/2025 from the soil
laboratory of ESALQ/USP, sample "YURI - SOLO 1", a routine Brazilian fertility
analysis. Every one of its four usable variables is in a unit SMAF's curves
are not defined on, and none of the four differences is visible in the number.
Read without declaring the units the report scores 0.69; read correctly it
scores 0.24.
"""

from __future__ import annotations

import pandas as pd
import pytest

from esmaf_core import engine, units as un
from esmaf_core.models import load_model
from esmaf_core.parameters import SiteFactors
from esmaf_core.validation import check
from esmaf_core.weights import WeightConfig

MODEL = load_model("esmaf-2.0")

#: Clayey Oxisol under maize at Piracicaba, phosphorus by ion-exchange resin.
CLAYEY = SiteFactors(region=2, season=1, climate=1, slope=2, texture=5,
                     mineral=3, organic_matter=3, iron_oxide=1, weathering=3,
                     p_method=5, ec_method=1)

#: The laudo, transcribed as printed.
LAUDO = {
    "site": "YURI - SOLO 1", "land_use": "Cropland", "management": "NT",
    "crop": "Corn, grain", "depth": "0-20",
    "pH": 6.17,    # pH CaCl2
    "SOC": 3.7,    # M.O. colorimetrica, g/dm3
    "P": 3.0,      # fosforo resina, mg/dm3
    "K": 0.2,      # potassio resina, mmolc/dm3
}
AS_PRINTED = {"pH": "cacl2", "SOC": "om_g/dm3", "P": "mg/dm3", "K": "mmolc/dm3"}


def run(units=None, rule="by_texture", row=None, factors=CLAYEY):
    frame = pd.DataFrame([row or LAUDO])
    return engine.run(frame, factors, WeightConfig(scheme="equal_components"),
                      engine.AnalysisOptions(units=units or {}, density_rule=rule))


# ------------------------------------------------------- reading the header


@pytest.mark.parametrize("header,indicator,expected", [
    ("P_mg/dm3", "P", "mg/dm3"),
    ("P_mg/kg", "P", "mg/kg"),
    ("P", "P", None),                      # says nothing, so nothing is assumed
    ("K_mmolc/dm3", "K", "mmolc/dm3"),
    ("K_cmolc/dm3", "K", "cmolc/dm3"),
    ("MO_g/dm3", "SOC", "om_g/dm3"),
    ("SOC_pct", "SOC", "pct"),
    ("SOC_g/kg", "SOC", "g/kg"),
    ("pH_CaCl2", "pH", "cacl2"),
    ("pH_H2O", "pH", "water"),
    ("pH", "pH", None),
    ("AWC_cm3/cm3", "AWC", "cm3/cm3"),
    ("WFPS_pct", "WFPS", "pct"),
    ("EC_uS/cm", "EC", "uS/cm"),
])
def test_a_header_that_states_its_unit_is_read(header, indicator, expected):
    assert un.from_header(indicator, header) == expected


def test_a_bare_column_name_is_never_guessed_at():
    """The whole point. "P" could be mg/kg or mg/dm3 and only the user knows."""
    for indicator in ("P", "K", "SOC", "pH"):
        assert un.from_header(indicator, indicator) is None


# ------------------------------------------------------------- conversions


def test_the_laudo_scores_three_times_too_high_when_the_units_are_ignored():
    """The number this whole mechanism exists to prevent."""
    ignored = run().scores.iloc[0]
    declared = run(AS_PRINTED).scores.iloc[0]
    assert ignored["quality_index"] == pytest.approx(0.69, abs=0.01)
    assert declared["quality_index"] == pytest.approx(0.24, abs=0.01)


def test_organic_matter_per_volume_becomes_carbon_per_cent():
    row = run(AS_PRINTED, rule="assume_one").scores.iloc[0]
    # 3.7 g dm-3 of organic matter / 1.724 / 1.0 kg dm-3 / 10 = 0.215 %
    assert row["SOC"] == pytest.approx(3.7 / 1.724 / 10, abs=1e-4)
    assert row["SOC_score"] == pytest.approx(0.03, abs=0.01)


def test_potassium_as_charge_per_volume_becomes_milligrams_per_kilogram():
    row = run(AS_PRINTED, rule="assume_one").scores.iloc[0]
    assert row["K"] == pytest.approx(0.2 * 39.0983, abs=1e-3)
    assert row["K_score"] > 0.1, "0.2 read as mg/kg would score essentially zero"


def test_ph_in_calcium_chloride_is_lifted_onto_the_water_basis():
    row = run(AS_PRINTED).scores.iloc[0]
    assert row["pH"] == pytest.approx(6.17 + 0.6, abs=1e-6)


def test_the_offset_comes_from_the_model_not_from_the_code():
    assert un.ph_offset(MODEL, "water") == 0.0
    assert un.ph_offset(MODEL, "cacl2") == pytest.approx(0.6)
    assert un.ph_offset(MODEL, "kcl") == pytest.approx(1.0)


# ----------------------------------------------- the density that converts


def test_the_sieved_sample_density_comes_from_the_texture_class():
    """Not from the field bulk density, which describes a destroyed structure."""
    heavy, how = un.sieved_density(MODEL, "by_texture", 5)
    light, _ = un.sieved_density(MODEL, "by_texture", 1)
    assert heavy < light, "a sieved clay packs more loosely than a sieved sand"
    assert "texture class 5" in how


def test_assuming_one_is_offered_and_says_so():
    value, how = un.sieved_density(MODEL, "assume_one", 5)
    assert value == 1.0
    assert "assumed" in how


def test_the_two_density_rules_differ_but_not_by_much():
    """Getting the kind of unit right matters far more than the density."""
    one = run(AS_PRINTED, rule="assume_one").scores.iloc[0]["quality_index"]
    texture = run(AS_PRINTED, rule="by_texture").scores.iloc[0]["quality_index"]
    assert one != texture
    assert abs(one - texture) < 0.05


def test_volumetric_water_content_uses_the_field_bulk_density():
    """Water per volume refers to intact soil, so the divisor is not the same.

    This is the one conversion where the field bulk density is right, and it
    is the reason the two kinds of "per volume" are kept apart.
    """
    row = dict(LAUDO, AWC=0.26, BD=1.30)
    result = run({"AWC": "cm3/cm3"}, row=row)
    assert result.scores["AWC"].iloc[0] == pytest.approx(0.26 / 1.30, abs=1e-6)


def test_volumetric_water_content_without_a_bulk_density_is_refused():
    """Left out rather than scored on the wrong basis, and the reason is given."""
    row = dict(LAUDO, AWC=0.26)
    result = run({"AWC": "cm3/cm3"}, row=row)
    assert "AWC_score" not in result.scores.columns
    assert any("bulk density" in w for w in result.warnings)


def test_the_two_volume_bases_are_not_confused_with_each_other():
    assert un.get("P", "mg/dm3").volume_basis
    assert not un.get("P", "mg/dm3").bulk_basis
    assert un.get("AWC", "cm3/cm3").bulk_basis
    assert not un.get("AWC", "cm3/cm3").volume_basis


# ----------------------------------------------------------- what is recorded


def test_every_conversion_is_written_into_the_provenance():
    result = run(AS_PRINTED)
    recorded = {c["indicator"]: c for c in result.provenance["unit_conversions"]}
    assert set(recorded) == {"pH", "SOC", "P", "K"}
    assert "Van Bemmelen" in recorded["SOC"]["detail"]
    assert "texture class 5" in recorded["P"]["detail"]
    assert result.provenance["sieved_density_rule"] == "by_texture"
    assert result.provenance["units_declared"]["K"] == "mmolc/dm3"


def test_the_values_the_user_supplied_are_kept_untouched():
    result = run(AS_PRINTED)
    assert result.supplied["SOC"].iloc[0] == 3.7
    assert result.scores["SOC"].iloc[0] != 3.7


def test_estimating_carbon_from_organic_matter_is_flagged_not_hidden():
    result = run(AS_PRINTED)
    assert any("Van Bemmelen" in w and "preferable" in w for w in result.warnings)


def test_a_converted_ph_is_flagged_too():
    result = run(AS_PRINTED)
    assert any("measured in water" in w for w in result.warnings)


# ---------------------------------------------------------------- the check


def test_a_column_with_no_declared_unit_stops_the_analysis():
    report = check(pd.DataFrame([LAUDO]), CLAYEY.as_dict(), WeightConfig(),
                   "esmaf-2.0", units={"pH": "cacl2"})
    assert not report.can_run
    missing = {f.scope for f in report.errors if "unit" in f.where}
    assert {"SOC", "P", "K"} <= missing


def test_bulk_density_needs_no_declaration_because_the_choice_changes_nothing():
    assert not un.must_be_declared("BD")
    assert un.must_be_declared("P")
    assert un.must_be_declared("SOC")


def test_potassium_declared_in_the_wrong_unit_is_caught_by_its_size():
    """0.2 is an ordinary number in mmolc dm-3 and an impossible one in mg kg-1."""
    message = un.review("K", pd.Series([0.2, 0.1, 0.3]), "mg/kg", MODEL)
    assert message is not None
    assert "mmolc" in message


def test_a_correct_declaration_raises_nothing():
    assert un.review("K", pd.Series([0.2, 0.1]), "mmolc/dm3", MODEL) is None
    assert un.review("K", pd.Series([210, 180]), "mg/kg", MODEL) is None
    assert un.review("P", pd.Series([3.0, 17.9]), "mg/kg", MODEL) is None


def test_the_size_check_cannot_catch_everything_and_does_not_pretend_to():
    """Organic matter of 3.7 g dm-3 and carbon of 3.7 % are both believable.

    Recorded as a test because it is the argument for asking rather than
    inferring: no amount of cleverness about the numbers can separate these
    two, and the difference between them is a score of 0.03 and one of 1.00.
    """
    assert un.review("SOC", pd.Series([3.7, 2.0]), "pct", MODEL) is None
    assert un.review("SOC", pd.Series([3.7, 2.0]), "om_g/dm3", MODEL) is None


# --------------------------------------------------------------- presets


def test_the_brazilian_preset_matches_what_the_laudo_actually_says():
    preset = un.preset("br_routine")
    for key, unit_id in AS_PRINTED.items():
        assert preset.units[key] == unit_id


def test_the_template_preset_is_what_the_curves_expect():
    assert un.preset("esmaf").units == un.DEFAULT_UNIT


def test_the_template_states_its_own_units_in_its_headers(tmp_path):
    from esmaf_core import importer

    report = importer.load(importer.write_template(tmp_path / "t.xlsx"))
    stated = {m.target: m.unit for m in report.mappings if m.target in un.UNITS}
    for key, unit_id in un.DEFAULT_UNIT.items():
        if key == "SAR":      # only one possible unit; the header need not say
            continue
        assert stated.get(key) == unit_id, f"{key} header does not state its unit"


# ------------------------------------------------------------ presets


def test_the_selector_keeps_the_preset_that_was_actually_chosen():
    """Two presets can ask for the same units, and the choice must survive.

    SMAF's curves are defined per kilogram, so the eSMAF template and the
    Embrapa mass basis are the same units seen from two directions. Without
    a preference, picking "Mass basis" snapped back to "eSMAF template" and
    looked like a dead entry in the list.
    """
    keys = ["P", "K", "SOC", "pH"]
    mass = {k: un.preset("embrapa").units[k] for k in keys}
    assert un.matching_preset(mass, keys, prefer="embrapa") == "embrapa"
    assert un.matching_preset(mass, keys, prefer="esmaf") == "esmaf"
    assert un.matching_preset(mass, keys) == "esmaf", "first match, with no preference"
    assert "esmaf" in un.equivalent_presets("embrapa", keys)


def test_a_preference_cannot_resurrect_a_preset_the_units_contradict():
    keys = ["P", "K", "SOC", "pH"]
    laudo = {"P": "mg/dm3", "K": "mmolc/dm3", "SOC": "om_g/dm3", "pH": "cacl2"}
    assert un.matching_preset(laudo, keys, prefer="embrapa") == "br_routine"
    assert un.matching_preset(dict(laudo, pH="water"), keys,
                              prefer="br_routine") is None


def test_a_volumetric_column_tells_the_presets_apart():
    """They only coincide for a dataset with nothing measured per volume."""
    assert un.equivalent_presets("embrapa", ["P", "K"]) == ["esmaf"]
    assert un.equivalent_presets("br_routine", ["P", "K"]) == []
