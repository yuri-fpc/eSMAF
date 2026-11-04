"""The crop database: what is in it, what people call it, and what is missing.

The database is a copy of the one the eSMAF website carries, and it is the
single place where the pH, EC and phosphorus curves get their crop-specific
shape. Two things about it need holding down: the names real spreadsheets use
have to reach the right entry, and the entries that carry no salinity
threshold must not be allowed to look as though they do.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from esmaf_core.crops import (UnknownCrop, _read_crops, _resolve_borrowed,
                              find_crop, get_crop, load_crops)

#: The thirteen entries whose salinity threshold is zero in the source
#: database. All six Brazilian entries are among them, and so is every
#: soybean response class.
WITHOUT_THRESHOLD = {
    "Ryegrass, annual", "Oak, white", "Brazilian cerrado",
    "Brazilian atlantic forest", "Brazilian brachiaria", "Brazilian sugarcane",
    "Soybean I", "Soybean II", "Soybean III", "Soybean IV", "Eucalyptus",
    "Mangrove", "Brazilian caatinga",
}


def test_the_whole_database_is_present():
    assert len(load_crops()) == 117


@pytest.mark.parametrize("typed,expected", [
    ("BCerrado", "Brazilian cerrado"),
    ("Cerrado", "Brazilian cerrado"),
    ("cerrado ", "Brazilian cerrado"),
    ("Mata Atlântica", "Brazilian atlantic forest"),
    ("Caatinga", "Brazilian caatinga"),
    ("Manguezal", "Mangrove"),
    ("Braquiária", "Brazilian brachiaria"),
    ("pastagem", "Brazilian brachiaria"),
    ("BSugarcane", "Brazilian sugarcane"),
    ("Cana-de-açúcar", "Brazilian sugarcane"),
    ("cana", "Brazilian sugarcane"),
    ("Eucalipto", "Eucalyptus"),
    ("Soja II", "Soybean II"),
    ("soja2", "Soybean II"),
    ("milho", "Corn, grain"),
    ("Corn, grain", "Corn, grain"),
])
def test_the_names_people_actually_type_reach_the_right_entry(typed, expected):
    """The template ships "BCerrado"; the web version could not resolve it."""
    assert get_crop(typed).name == expected


def test_a_name_that_is_merely_similar_is_never_substituted_silently():
    with pytest.raises(UnknownCrop) as raised:
        get_crop("Soyabean")
    assert "Soybean" in " ".join(raised.value.suggestions)


def test_the_entries_without_a_salinity_threshold_are_the_known_thirteen():
    """A guard on the data, so a future edit cannot lose or invent one."""
    absent = {c.name for c in load_crops() if not c.has_salinity_threshold}
    assert absent == WITHOUT_THRESHOLD


def test_nothing_borrows_a_salinity_threshold_unless_the_database_says_so():
    assert all(crop.ec_from == "" for crop in load_crops())


def test_ec_from_lets_the_database_state_where_a_threshold_came_from():
    borrowed = _resolve_borrowed(tuple(
        replace(c, ec_from="Soybean") if c.name.startswith("Soybean ") else c
        for c in _read_crops()))
    by_name = {c.name: c for c in borrowed}
    source = by_name["Soybean"]
    for name in ("Soybean I", "Soybean II", "Soybean III", "Soybean IV"):
        assert by_name[name].ec_threshold_saturation == source.ec_threshold_saturation
        assert by_name[name].ec_decline_rate == source.ec_decline_rate
        assert by_name[name].ec_from == "Soybean", "the source has to stay on record"


def test_ec_from_cannot_overwrite_a_threshold_the_crop_already_has():
    """It fills a gap; it does not override a measured parameter."""
    borrowed = _resolve_borrowed(tuple(
        replace(c, ec_from="Mangrove") if c.name == "Corn, grain" else c
        for c in _read_crops()))
    corn = next(c for c in borrowed if c.name == "Corn, grain")
    assert corn.ec_threshold_saturation == 1.8
    assert corn.ec_from == ""


def test_ec_from_pointing_at_something_unknown_is_ignored_not_guessed():
    borrowed = _resolve_borrowed(tuple(
        replace(c, ec_from="Soja II") if c.name == "Eucalyptus" else c
        for c in _read_crops()))
    eucalyptus = next(c for c in borrowed if c.name == "Eucalyptus")
    assert not eucalyptus.has_salinity_threshold
    assert eucalyptus.ec_from == ""


def test_a_borrowed_threshold_is_reported_in_the_analysis():
    import pandas as pd
    from esmaf_core import crops as crops_module, engine
    from esmaf_core.parameters import SiteFactors
    from esmaf_core.weights import WeightConfig

    original = crops_module.load_crops
    patched = _resolve_borrowed(tuple(
        replace(c, ec_from="Soybean") if c.name == "Soybean II" else c
        for c in _read_crops()))
    crops_module.load_crops = lambda: patched
    crops_module._index.cache_clear()
    try:
        row = {"land_use": "Cropland", "management": "NT", "crop": "Soybean II",
               "depth": "0-10", "EC": 1.2, "pH": 6.0, "K": 300.0}
        factors = SiteFactors(region=2, season=1, climate=1, slope=1, texture=3,
                              mineral=3, organic_matter=3, iron_oxide=2,
                              weathering=3, p_method=2, ec_method=1)
        result = engine.run(pd.DataFrame([row]), factors, WeightConfig())
        assert pd.notna(result.scores["EC_score"].iloc[0])
        assert any("taken from 'Soybean'" in w for w in result.warnings)
    finally:
        crops_module.load_crops = original
        crops_module._index.cache_clear()
