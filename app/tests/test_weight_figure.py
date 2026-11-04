"""The weight bar has to add up, because the reader will add it up.

The figure is the only place where the two weights a user sets are multiplied
out: an indicator given 80 % inside a component that carries 20 % of the index
contributes 16 %. Rounding each segment on its own breaks that arithmetic
visibly -- four indicators of 8.33 % printed as 8 % sit under a component
labelled 33 % -- so the percentages are apportioned by largest remainder, twice:
components to 100, then each component's indicators to that component.
"""

from __future__ import annotations

import pytest

from esmaf_core import charts
from esmaf_core.charts import ChartContext, _largest_remainder, _precision
from esmaf_core.indicators import BY_KEY, COMPONENTS
from esmaf_core.weights import WeightConfig, apply

#: (indicator weights within their component, component shares of the index)
CASES = {
    "equal components, two each": (
        {"BD": .5, "AGG": .5, "pH": .5, "K": .5, "SOC": .5, "BG": .5},
        {"physical": 1 / 3, "chemical": 1 / 3, "biological": 1 / 3}),
    "all thirteen": (
        {**{k: .25 for k in ("BD", "AGG", "WFPS", "AWC")},
         **{k: .20 for k in ("pH", "EC", "P", "K", "SAR")},
         **{k: .25 for k in ("SOC", "MBC", "BG", "PMN")}},
        {"physical": 1 / 3, "chemical": 1 / 3, "biological": 1 / 3}),
    "equal indicators": (
        {**{k: .25 for k in ("BD", "AGG", "WFPS", "AWC")},
         **{k: .20 for k in ("pH", "EC", "P", "K", "SAR")},
         **{k: .25 for k in ("SOC", "MBC", "BG", "PMN")}},
        {"physical": 4 / 13, "chemical": 5 / 13, "biological": 4 / 13}),
    "the worked custom example": (
        {"BD": .25 / .35, "AGG": .10 / .35, "pH": .30 / .45, "K": .15 / .45,
         "SOC": .15 / .20, "BG": .05 / .20},
        {"physical": .35, "chemical": .45, "biological": .20}),
    "a two per cent sliver": (
        {"BD": .80, "AGG": .18, "WFPS": .02, "pH": .5, "K": .5,
         "SOC": .5, "BG": .5},
        {"physical": .20, "chemical": .60, "biological": .20}),
    "one component only": (
        {"SOC": .5, "MBC": .3, "BG": .2}, {"biological": 1.0}),
}


def displayed(indicator_weights, component_weights):
    """The numbers the figure prints, in the units it prints them in."""
    shares = [v * component_weights[BY_KEY[k].component]
              for k, v in indicator_weights.items()]
    scale = _precision(list(component_weights.values()) + shares)
    components = dict(zip(
        component_weights,
        _largest_remainder(list(component_weights.values()), 100 * scale)))
    segments: dict[str, int] = {}
    for component in component_weights:
        members = [(k, v) for k, v in indicator_weights.items()
                   if BY_KEY[k].component == component]
        segments.update(dict(zip(
            [k for k, _ in members],
            _largest_remainder([v for _, v in members], components[component]))))
    return scale, components, segments


@pytest.mark.parametrize("name", list(CASES))
def test_the_components_add_up_to_one_hundred_per_cent(name):
    scale, components, _ = displayed(*CASES[name])
    assert sum(components.values()) == 100 * scale


@pytest.mark.parametrize("name", list(CASES))
def test_each_components_indicators_add_up_to_that_component(name):
    indicator_weights, component_weights = CASES[name]
    scale, components, segments = displayed(indicator_weights, component_weights)
    for component in component_weights:
        members = [k for k in indicator_weights
                   if BY_KEY[k].component == component]
        assert sum(segments[k] for k in members) == components[component], component


@pytest.mark.parametrize("name", list(CASES))
def test_every_segment_is_within_a_rounding_step_of_the_truth(name):
    """Balancing the totals must not move a number further than it can round."""
    indicator_weights, component_weights = CASES[name]
    scale, _, segments = displayed(indicator_weights, component_weights)
    for key, value in segments.items():
        truth = indicator_weights[key] * component_weights[BY_KEY[key].component]
        assert abs(value / scale - truth * 100) <= 1.0 / scale + 1e-9, key


def test_whole_numbers_stay_whole_and_thirds_do_not_pretend_to_be():
    scale, components, segments = displayed(*CASES["the worked custom example"])
    assert scale == 1, "25, 10, 30, 15, 15, 5 need no decimal place"
    assert segments["BD"] == 25 and segments["BG"] == 5
    assert components["physical"] == 35

    scale, _, _ = displayed(*CASES["equal components, two each"])
    assert scale == 10, "16.667 printed as 17 four times and 16 twice reads as a bug"


def test_the_worked_example_from_the_interface_text():
    """80 % of a component that carries 20 % of the index is 16 % of the index."""
    _, _, segments = displayed({"BD": .80, "AGG": .20, "pH": 1.0, "SOC": 1.0},
                               {"physical": .20, "chemical": .40,
                                "biological": .40})
    assert segments["BD"] == 16


def test_the_figure_draws_for_every_case():
    for name, (indicator_weights, component_weights) in CASES.items():
        fig = charts.weight_tree(indicator_weights, component_weights,
                                 ChartContext("How weight flows to the index"))
        assert fig.axes, name


def test_it_also_draws_from_what_the_engine_actually_produces():
    available = {"BD", "AGG", "pH", "K", "SOC", "BG"}
    for scheme in ("equal_components", "equal_indicators"):
        applied = apply(WeightConfig(scheme=scheme), available)
        fig = charts.weight_tree(applied.indicator, applied.component,
                                 ChartContext("How weight flows to the index"))
        assert fig.axes, scheme


def test_an_empty_weighting_does_not_raise():
    fig = charts.weight_tree({}, {}, ChartContext("How weight flows to the index"))
    assert fig.axes


def test_custom_weights_are_read_within_each_component():
    """The rule the interface now states: each component's own weights make 100.

    Doubling one component's internal weights changes nothing, because they are
    proportions inside that component; only the component weights move the index.
    """
    available = {"BD", "AGG", "pH", "K", "SOC", "BG"}
    one = apply(WeightConfig(
        scheme="custom",
        indicator_weights={"BD": 75, "AGG": 25, "pH": 50, "K": 50,
                           "SOC": 50, "BG": 50},
        component_weights={"physical": 50, "chemical": 25, "biological": 25},
    ), available)
    two = apply(WeightConfig(
        scheme="custom",
        indicator_weights={"BD": 150, "AGG": 50, "pH": 10, "K": 10,
                           "SOC": 1, "BG": 1},
        component_weights={"physical": 50, "chemical": 25, "biological": 25},
    ), available)
    assert one.indicator == pytest.approx(two.indicator)
    assert one.component == pytest.approx(two.component)
    assert one.indicator["BD"] == pytest.approx(0.75)
    assert one.indicator["BD"] * one.component["physical"] == pytest.approx(0.375)


def test_the_validator_asks_each_component_for_one_hundred_separately():
    config = WeightConfig(
        scheme="custom",
        indicator_weights={"BD": 60, "AGG": 30,          # 90, short
                           "pH": 50, "K": 50,            # 100, fine
                           "SOC": 50, "BG": 50},
        component_weights={"physical": 100 / 3, "chemical": 100 / 3,
                           "biological": 100 / 3},
    )
    problems = config.validate()
    assert any("Physical" in p and "90" in p for p in problems)
    assert not any("Chemical" in p for p in problems)


# ------------------------------------------------- what the interface offers


def test_equal_shares_add_up_to_exactly_one_hundred():
    """33.3333 three times is 99.9999, and the user is asked for 100."""
    from esmaf_core.weights import _split_hundred

    for count in range(1, 14):
        parts = _split_hundred(count)
        assert len(parts) == count
        assert sum(parts) == pytest.approx(100.0, abs=1e-9), count
        assert max(parts) - min(parts) <= 0.0101, count


def test_defaults_are_seeded_over_the_indicators_the_dataset_has():
    """The boxes the user is shown must already add up to the 100 % asked for.

    Five chemical indicators exist; a dataset with three of them used to be
    seeded with 20 % each, handing the user a total of 60 % and an error
    message they had not caused.
    """
    available = {"BD", "AGG", "pH", "P", "K", "SOC", "BG"}
    config = WeightConfig(scheme="custom")
    seeded = config.seed_indicator_weights(available)
    assert set(seeded) == available
    for component in COMPONENTS:
        members = config.members(component, available)
        assert sum(seeded[k] for k in members) == pytest.approx(100.0), component
    assert config.validate(available) == []


def test_a_component_with_no_data_is_not_asked_to_add_up():
    """A laudo with no physical column cannot be given a physical total."""
    available = {"pH", "K", "SOC", "BG"}
    config = WeightConfig(scheme="custom")
    config.indicator_weights = config.seed_indicator_weights(available)
    config.component_weights = config.seed_component_weights(available)
    assert "physical" not in config.component_weights
    assert config.validate(available) == []
    assert sum(config.component_weights.values()) == pytest.approx(100.0)


def test_an_indicator_given_no_weight_is_named_rather_than_drawn():
    """A zero-width segment cannot hold a label, and two of them collide."""
    indicator_weights = {"BD": .80, "AGG": .20, "WFPS": 0.0, "AWC": 0.0,
                         "pH": 1.0, "SOC": 1.0}
    component_weights = {"physical": .20, "chemical": .40, "biological": .40}
    fig = charts.weight_tree(indicator_weights, component_weights,
                             ChartContext("How weight flows to the index"))
    texts = [t.get_text() for t in fig.axes[0].texts]
    assert any(t.startswith("Given no weight:") for t in texts)
    assert "WFPS" not in texts and "AWC" not in texts
    assert "16%" in texts or "16.0%" in texts


def test_the_preset_selector_reads_its_state_from_the_units():
    from esmaf_core import units as un

    laudo = {"pH": "cacl2", "P": "mg/dm3", "K": "mmolc/dm3", "SOC": "om_g/dm3"}
    keys = list(laudo)
    assert un.matching_preset(laudo, keys) == "br_routine"
    assert un.matching_preset(dict(laudo, pH="water"), keys) is None
    assert un.matching_preset(un.DEFAULT_UNIT, keys) == "esmaf"
    assert un.matching_preset({"pH": "cacl2"}, keys) is None, "incomplete is no preset"
