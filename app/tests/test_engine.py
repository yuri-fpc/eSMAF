"""Behaviour of the engine around missing data, weights and partial indices.

These are the behaviours that changed relative to the web version, so each
test states the expectation in the terms a soil scientist would use rather
than in terms of the implementation.
"""

from __future__ import annotations

import pandas as pd
import pytest

from esmaf_core import engine
from esmaf_core.parameters import SiteFactors
from esmaf_core.validation import check
from esmaf_core.weights import WeightConfig, apply, index_name

CROP = "Corn, grain"

PERFECT = {
    "land_use": "Cropland", "management": "NT", "crop": CROP, "depth": "0-10",
    "BD": 1.0, "AGG": 95.0, "WFPS": 0.60, "AWC": 0.30,
    "pH": 6.3, "P": 25.0, "K": 400.0, "SAR": 0.0, "EC": 0.5,
    "SOC": 6.0, "PMN": 40.0, "MBC": 1200.0, "BG": 500.0,
}

FACTORS = SiteFactors(region=2, season=1, climate=1, slope=1, texture=3,
                      mineral=3, organic_matter=3, iron_oxide=2, weathering=3,
                      p_method=2, ec_method=1)


def run(rows, config=None, **overrides):
    frame = pd.DataFrame(rows)
    return engine.run(frame, FACTORS, config or WeightConfig(scheme="equal_components"))


# ---------------------------------------------------------------- missing data


def test_a_missing_indicator_does_not_lower_the_component_score():
    """The defect that mattered most in the web version.

    A physical component built from three indicators instead of four should be
    scored on those three, not scored on four with one contributing zero.
    """
    full = run([PERFECT]).scores
    without_awc = run([{k: v for k, v in PERFECT.items() if k != "AWC"}]).scores

    assert full["physical_component"].iloc[0] == pytest.approx(
        without_awc["physical_component"].iloc[0], abs=0.02
    )
    assert without_awc["physical_component"].iloc[0] > 0.9


def test_one_empty_cell_does_not_remove_the_indicator_for_everyone_else():
    rows = [dict(PERFECT, sample=1), dict(PERFECT, sample=2, SOC=None)]
    result = run(rows)
    assert "SOC_score" in result.scores.columns
    assert pd.notna(result.scores["SOC_score"].iloc[0])
    assert pd.isna(result.scores["SOC_score"].iloc[1])
    # The row that lost SOC still gets a biological component from the rest.
    assert pd.notna(result.scores["biological_component"].iloc[1])


def test_a_row_missing_everything_in_one_component_still_scores_the_others():
    row = {k: v for k, v in PERFECT.items()
           if k not in ("SOC", "PMN", "MBC", "BG")}
    result = run([row])
    assert result.scores["biological_component"].iloc[0] is None or \
        pd.isna(result.scores["biological_component"].iloc[0])
    assert result.scores["physical_component"].iloc[0] > 0
    assert not result.complete_index


# -------------------------------------------------------------- partial index


def test_a_partial_index_can_still_reach_one():
    """Two components must be renormalised over two, not over three."""
    row = {k: v for k, v in PERFECT.items()
           if k not in ("BD", "AGG", "WFPS", "AWC")}
    result = run([row])
    assert result.index_label == "Chemical-Biological Quality Index"
    assert result.index_column == "quality_index"
    value = result.scores["quality_index"].iloc[0]
    chemical = result.scores["chemical_component"].iloc[0]
    biological = result.scores["biological_component"].iloc[0]
    assert value == pytest.approx((chemical + biological) / 2, abs=0.01)
    assert value > 0.9


def test_a_partial_index_is_flagged_as_partial():
    row = {k: v for k, v in PERFECT.items() if k not in ("BD", "AGG", "WFPS", "AWC")}
    result = run([row])
    assert not result.complete_index
    assert any("partial index" in w for w in result.warnings)


@pytest.mark.parametrize("components,expected", [
    (("physical", "chemical", "biological"), "Soil Health Index"),
    (("chemical", "biological"), "Chemical-Biological Quality Index"),
    (("physical", "chemical"), "Physico-Chemical Quality Index"),
    (("physical",), "Physical Quality Index"),
])
def test_index_is_named_for_the_components_it_contains(components, expected):
    assert index_name(components) == expected


# -------------------------------------------------------------------- weights


def test_equal_component_weights_give_each_component_one_third():
    applied = apply(WeightConfig(scheme="equal_components"),
                    {"BD", "AGG", "pH", "K", "SOC", "BG"})
    assert set(applied.component) == {"physical", "chemical", "biological"}
    for weight in applied.component.values():
        assert weight == pytest.approx(1 / 3)


def test_equal_indicator_weights_give_components_weight_by_indicator_count():
    """Four physical and two chemical indicators means 4:2, not 1:1."""
    applied = apply(WeightConfig(scheme="equal_indicators"),
                    {"BD", "AGG", "WFPS", "AWC", "pH", "K"})
    assert applied.component["physical"] == pytest.approx(4 / 6)
    assert applied.component["chemical"] == pytest.approx(2 / 6)


def test_indicator_weights_sum_to_one_within_each_component():
    applied = apply(WeightConfig(scheme="equal_components"),
                    {"BD", "AGG", "pH", "P", "K", "SOC"})
    physical = sum(v for k, v in applied.indicator.items() if k in {"BD", "AGG"})
    chemical = sum(v for k, v in applied.indicator.items() if k in {"pH", "P", "K"})
    assert physical == pytest.approx(1.0)
    assert chemical == pytest.approx(1.0)


def test_custom_weights_that_do_not_total_one_hundred_are_rejected():
    config = WeightConfig(scheme="custom",
                          indicator_weights={"BD": 40.0, "AGG": 40.0, "WFPS": 10.0, "AWC": 5.0},
                          component_weights={"physical": 50.0, "chemical": 30.0,
                                             "biological": 20.0})
    problems = config.validate()
    assert any("95" in p for p in problems)


def test_excluding_an_indicator_removes_it_from_the_result():
    config = WeightConfig(scheme="equal_components", excluded={"AGG"})
    result = run([PERFECT], config)
    assert "AGG_score" not in result.scores.columns
    assert "AGG" not in result.available_indicators


# ---------------------------------------------------------------------- WFPS


def test_wfps_splits_its_weight_between_its_two_scores():
    result = run([PERFECT])
    assert "WFPS_BiolAct_score" in result.scores.columns
    assert "WFPS_EnvProtect_score" in result.scores.columns
    assert result.weights.indicator["WFPS"] == pytest.approx(0.25)


def test_wfps_given_as_a_percentage_is_rejected_by_the_check():
    from esmaf_core import units as un

    frame = pd.DataFrame([dict(PERFECT, WFPS=60.0)])
    report = check(frame, FACTORS.as_dict(), WeightConfig(), "esmaf-2.0",
                   units=dict(un.DEFAULT_UNIT))
    assert any(f.scope == "WFPS" and f.severity == "error" for f in report.findings)
    assert not report.can_run


# ------------------------------------------------------------------ SAR / EC


def test_sar_uses_a_saturation_paste_basis_when_ec_was_measured_at_one_to_one():
    """A 1:1 reading of 0.15 is about 0.27 on a saturation paste.

    The two sit on opposite sides of the first SAR branch threshold, so the
    conversion changes which polynomial applies.
    """
    factors = SiteFactors(**dict(FACTORS.as_dict(), ec_method=2))
    frame = pd.DataFrame([dict(PERFECT, EC=0.15, SAR=5.0)])
    corrected = engine.run(frame, factors, WeightConfig())
    legacy = engine.run(frame, factors, WeightConfig(),
                        engine.AnalysisOptions(model_id="esmaf-1.0-legacy"))
    assert corrected.scores["SAR_score"].iloc[0] != legacy.scores["SAR_score"].iloc[0]


def test_a_crop_without_a_salinity_threshold_does_not_score_ec_as_perfect():
    """Silence is safer than a fabricated 1.00.

    Every Brazilian entry added to the crop database has T = 0, which the web
    version turned into a score of 1.00 for any conductivity whatsoever.
    """
    row = dict(PERFECT, crop="Brazilian sugarcane", EC=8.0)
    result = run([row])
    assert "EC_score" not in result.scores.columns or \
        pd.isna(result.scores["EC_score"].iloc[0])
    assert any("salinity threshold" in w for w in result.warnings)


# ------------------------------------------------------------------- grouping


def test_aggregation_reports_mean_spread_and_count_per_group():
    rows = [dict(PERFECT, sample=i, SOC=soc)
            for i, soc in enumerate([2.0, 3.0, 4.0], start=1)]
    result = run(rows)
    assert len(result.aggregated) == 1
    row = result.aggregated.iloc[0]
    assert row["SOC_score_count"] == 3
    assert row["SOC_score_std"] > 0


def test_groups_are_kept_apart():
    rows = [dict(PERFECT, management="NT", sample=1),
            dict(PERFECT, management="CT", sample=1, SOC=1.0)]
    result = run(rows)
    assert len(result.aggregated) == 2


# --------------------------------------------------------------- provenance


def test_every_result_records_how_it_was_produced():
    result = run([PERFECT])
    p = result.provenance
    for key in ("software_version", "model_id", "crop_db_version",
                "analysis_datetime", "factor_classes", "indicator_weights",
                "component_weights", "weighting_scheme", "index"):
        assert key in p, key
    assert p["factor_classes"]["texture"] == 3


def test_the_legacy_model_announces_itself_as_deprecated():
    result = engine.run(pd.DataFrame([PERFECT]), FACTORS, WeightConfig(),
                        engine.AnalysisOptions(model_id="esmaf-1.0-legacy"))
    assert any("deprecated" in w for w in result.warnings)


# --------------------------------------------------------- texture class five


def test_the_fifth_texture_class_is_available_and_changes_the_scores():
    """A clay above 60 % is not the same soil as a clay loam.

    The web version had no class 5, so both were scored with the class 4
    parameters. Compared at a bulk density where the two curves actually
    separate, the difference is large enough to change an interpretation.
    """
    heavy = SiteFactors(**dict(FACTORS.as_dict(), texture=5))
    fine = SiteFactors(**dict(FACTORS.as_dict(), texture=4))
    frame = pd.DataFrame([dict(PERFECT, BD=1.30, SOC=1.5)])
    a = engine.run(frame, heavy, WeightConfig()).scores
    b = engine.run(frame, fine, WeightConfig()).scores
    assert abs(a["BD_score"].iloc[0] - b["BD_score"].iloc[0]) > 0.05
    assert a["SOC_score"].iloc[0] != b["SOC_score"].iloc[0]


# ------------------------------------------------------ mandatory factors


def test_nothing_is_assumed_when_a_factor_class_was_not_chosen():
    """No defaults. A blank factor class stops the analysis, it does not guess.

    The same measurements score very differently under a different organic
    matter or texture class, so a default here would be a scientific decision
    taken on the user's behalf and then hidden from them.
    """
    from esmaf_core.parameters import ParameterError

    blank = SiteFactors()
    assert not blank.complete
    assert len(blank.missing) == 11
    with pytest.raises(ParameterError, match="not been selected"):
        engine.run(pd.DataFrame([PERFECT]), blank, WeightConfig())


def test_one_missing_factor_class_is_named_in_the_error():
    partial = SiteFactors(**dict(FACTORS.as_dict(), organic_matter=None))
    from esmaf_core.parameters import ParameterError
    with pytest.raises(ParameterError, match="organic matter"):
        engine.run(pd.DataFrame([PERFECT]), partial, WeightConfig())


def test_the_check_blocks_until_every_factor_class_is_chosen():
    """Including the ones no indicator in this dataset happens to use."""
    from esmaf_core import units as un

    frame = pd.DataFrame([PERFECT])
    selection = dict(FACTORS.as_dict())
    del selection["slope"]
    report = check(frame, selection, WeightConfig(), "esmaf-2.0",
                   units=dict(un.DEFAULT_UNIT))
    assert not report.can_run
    assert any("Slope" in f.where for f in report.errors)


def test_the_legacy_model_refuses_the_fifth_texture_class():
    heavy = SiteFactors(**dict(FACTORS.as_dict(), texture=5))
    with pytest.raises(Exception, match="not defined in model"):
        engine.run(pd.DataFrame([PERFECT]), heavy, WeightConfig(),
                   engine.AnalysisOptions(model_id="esmaf-1.0-legacy"))
