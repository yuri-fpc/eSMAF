"""Several places in one spreadsheet, each scored against its own curves.

The point of the site column is not organisation. It is that a sandy soil and
a clayey one must not be scored against the same curve, and that until now the
only way to avoid it was to keep one file per place. These tests hold down the
two halves of that: the names have to reach the right site, and each site's
samples have to be scored with that site's factor classes and no one else's.
"""

from __future__ import annotations

import pandas as pd
import pytest

from esmaf_core import engine, sites, units as un
from esmaf_core.parameters import ParameterError, SiteFactors
from esmaf_core.project import Project
from esmaf_core.validation import check
from esmaf_core.weights import WeightConfig

SANDY = SiteFactors(region=2, season=1, climate=1, slope=1, texture=1,
                    mineral=3, organic_matter=4, iron_oxide=2, weathering=3,
                    p_method=2, ec_method=1)
CLAYEY = SiteFactors(**dict(SANDY.as_dict(), texture=5, organic_matter=2,
                            iron_oxide=1))

#: These tests are about sites, not units, so every column is declared in the
#: unit the template asks for.
TEMPLATE_UNITS = dict(un.DEFAULT_UNIT)

SAMPLE = {
    "land_use": "Cropland", "management": "NT", "crop": "Corn, grain",
    "depth": "0-10", "BD": 1.25, "AGG": 62.0, "WFPS": 0.55, "AWC": 0.18,
    "pH": 5.9, "P": 18.0, "K": 210.0, "SOC": 2.2, "PMN": 24.0,
    "MBC": 640.0, "BG": 180.0,
}


def two_farms() -> pd.DataFrame:
    return pd.DataFrame([
        dict(SAMPLE, site="Fazenda do Seu Zé", sample=1),
        dict(SAMPLE, site="FAZENDA DO SEU ZE", sample=2),
        dict(SAMPLE, site="Empresa Jacutinga", sample=3),
        dict(SAMPLE, site="empresa jacutinga ", sample=4),
    ])


# ------------------------------------------------------------- reading names


def test_spelling_alone_never_makes_two_places():
    index = sites.build(two_farms()["site"])
    assert index.names == ["Empresa Jacutinga", "Fazenda do Seu Zé"]
    assert all(site.rows == 2 for site in index.sites)


@pytest.mark.parametrize("written", [
    "Fazenda do Seu Zé", "FAZENDA DO SEU ZE", "fazenda  do   seu  ze",
    "Fazenda Seu Zé", "fazenda-do-seu-ze", " Fazenda do Seu Zé ",
])
def test_the_same_name_written_differently_reaches_one_site(written):
    index = sites.build(two_farms()["site"])
    assert index.resolve(written) == "Fazenda do Seu Zé"


def test_the_spelling_that_was_used_most_is_the_one_shown():
    values = ["Sitio Boa Vista"] * 5 + ["SITIO BOA VISTA"] * 2
    assert sites.build(values).names == ["Sitio Boa Vista"]


def test_every_tidied_spelling_is_reported_not_hidden():
    index = sites.build(two_farms()["site"])
    notes = " ".join(index.spelling_notes())
    assert "FAZENDA DO SEU ZE" in notes and "Fazenda do Seu Zé" in notes


def test_two_places_that_merely_look_alike_stay_two_places():
    """The decision that they are one farm is a claim about the world."""
    index = sites.build(["Fazenda Guaraci", "Fazenda Guarasi"])
    assert len(index.sites) == 2
    assert [{s.first, s.second} for s in index.suggestions] == [
        {"Fazenda Guaraci", "Fazenda Guarasi"}]


def test_one_name_contained_in_another_is_proposed():
    """Ambiguous by nature: a second plot, or the same place written twice."""
    index = sites.build(["Sítio São João", "Sítio São João II"])
    assert len(index.sites) == 2
    assert len(index.suggestions) == 1


def test_genuinely_different_names_are_not_even_suggested():
    index = sites.build(["Fazenda Santa Rita", "Fazenda Santa Clara",
                         "Empresa Jacutinga"])
    assert len(index.sites) == 3
    assert index.suggestions == ()


def test_the_shared_first_word_of_a_farm_name_does_not_make_a_suggestion():
    """The defect this rule was rewritten for, found on a real dataset.

    Almost every farm in one file starts with the same word. Comparing whole
    strings, "Fazenda" alone carried two unrelated names to 0.82 and the
    application announced that Apiai and Areiao were "spelled almost the same".
    """
    for pair in (["Fazenda Apiaí", "Fazenda areião"],
                 ["Fazenda Rio Claro", "Fazenda Rio Preto"],
                 ["Talhão 1", "Talhão 2"],
                 ["Gleba Norte", "Gleba Sul"],
                 ["Área 1", "Área 2"]):
        index = sites.build(pair)
        assert len(index.sites) == 2, pair
        assert index.suggestions == (), pair


def test_a_single_letter_is_an_identifier_and_never_a_connective():
    """"Fazenda A" used to tidy down to "fazenda" and merge with "Fazenda"."""
    index = sites.build(["Fazenda A", "Fazenda B"])
    assert len(index.sites) == 2
    assert index.suggestions == ()

    index = sites.build(["Fazenda A", "Fazenda"])
    assert len(index.sites) == 2, "different names must never merge silently"
    assert len(index.suggestions) == 1, "but the pair is worth asking about"


def test_the_tidying_keeps_anything_that_could_be_an_identifier():
    """Connectives go; single letters and final words stay, whatever they are.

    The asymmetry is deliberate. Failing to merge two spellings costs the user
    one extra set of factor classes, which they can see and fix. Merging two
    places that were never the same pools two soils into one description and
    says nothing, so every doubtful case is resolved towards keeping them
    apart -- "Santa Rita e Sao Jose" keeps its "e" for that reason.
    """
    assert sites.canonical("Fazenda do Seu Zé") == "fazenda seu ze"
    assert sites.canonical("Área dos Coqueiros") == "area coqueiros"
    assert sites.canonical("Gleba E") == "gleba e"
    assert sites.canonical("Fazenda A") == "fazenda a"
    assert sites.canonical("Santa Rita e São José") == "santa rita e sao jose"


def test_a_confirmed_merge_joins_them_and_survives_in_the_project(tmp_path):
    values = ["Fazenda Seu Zé", "Fazenda seu José"]
    joined = sites.build(values, merges=[["Fazenda Seu Zé", "Fazenda seu José"]])
    assert len(joined.sites) == 1

    project = Project(mapped=pd.DataFrame({"site": values}),
                      site_merges=[["Fazenda Seu Zé", "Fazenda seu José"]])
    reopened = Project.load(project.save(tmp_path / "p.esmaf"))
    assert reopened.site_merges == [["Fazenda Seu Zé", "Fazenda seu José"]]
    assert len(reopened.site_index().sites) == 1


def test_a_file_without_the_column_is_one_unnamed_place():
    index = sites.build(None)
    assert index.names == [sites.SINGLE_SITE]
    assert not index.from_column
    assert not index.several


# -------------------------------------------------------------- scoring


def test_each_site_is_scored_with_its_own_factor_classes():
    """The whole reason the column exists.

    The same measurements under a sandy, low-organic-matter description and a
    heavy clay one must not produce the same score.
    """
    frame = two_farms()
    result = engine.run(frame, {"Fazenda do Seu Zé": SANDY,
                                "Empresa Jacutinga": CLAYEY}, WeightConfig())
    sandy = result.scores[result.scores["site"] == "Fazenda do Seu Zé"]
    clayey = result.scores[result.scores["site"] == "Empresa Jacutinga"]
    assert sandy["BD_score"].iloc[0] != clayey["BD_score"].iloc[0]
    assert sandy["SOC_score"].iloc[0] != clayey["SOC_score"].iloc[0]
    assert abs(sandy["soil_health_index"].iloc[0]
               - clayey["soil_health_index"].iloc[0]) > 0.01


def test_rows_of_one_site_all_get_that_site_description():
    frame = two_farms()
    result = engine.run(frame, {"Fazenda do Seu Zé": SANDY,
                                "Empresa Jacutinga": CLAYEY}, WeightConfig())
    for name in ("Fazenda do Seu Zé", "Empresa Jacutinga"):
        rows = result.scores[result.scores["site"] == name]
        assert rows["BD_score"].nunique() == 1, "same soil, same measurement"
    assert result.factors_for("Fazenda do Seu Zé").texture == 1
    assert result.factors_for("Empresa Jacutinga").texture == 5


def test_one_description_for_a_multi_site_file_still_works():
    """Several places that genuinely share a soil are an ordinary dataset."""
    result = engine.run(two_farms(), SANDY, WeightConfig())
    assert result.several_sites
    assert len({tuple(sorted(result.factors_for(n).as_dict().items()))
                for n in result.site_factors}) == 1
    assert result.scores["BD_score"].nunique() == 1


def test_a_site_left_undescribed_stops_the_analysis():
    """Falling back on another site's soil would be a hidden decision."""
    with pytest.raises(ParameterError, match="Empresa Jacutinga"):
        engine.run(two_farms(), {"Fazenda do Seu Zé": SANDY}, WeightConfig())


def test_the_check_names_the_site_of_every_missing_class():
    frame = two_farms()
    index = sites.build(frame["site"])
    report = check(frame, SANDY.as_dict(), WeightConfig(), "esmaf-2.0",
                   site_factors={"Fazenda do Seu Zé": SANDY.as_dict(),
                                 "Empresa Jacutinga": SiteFactors().as_dict()},
                   site_index=index, units=TEMPLATE_UNITS)
    assert not report.can_run
    assert all("Empresa Jacutinga" in f.where for f in report.errors)
    assert len(report.errors) == 11


def test_a_row_with_no_site_while_others_have_one_is_an_error():
    frame = two_farms()
    frame.loc[0, "site"] = ""
    report = check(frame, SANDY.as_dict(), WeightConfig(), "esmaf-2.0",
                   units=TEMPLATE_UNITS)
    assert not report.can_run
    assert any(f.scope == "site" for f in report.errors)


def test_the_similar_name_warning_does_not_block_the_analysis():
    frame = pd.DataFrame([dict(SAMPLE, site="Fazenda Guaraci", sample=1),
                          dict(SAMPLE, site="Fazenda Guarasi", sample=2)])
    index = sites.build(frame["site"])
    report = check(frame, SANDY.as_dict(), WeightConfig(), "esmaf-2.0",
                   site_index=index, units=TEMPLATE_UNITS)
    assert report.can_run, "a warning informs; only an error blocks"
    assert any("almost the same" in f.what for f in report.warnings)


# ------------------------------------------------------------- provenance


def test_every_site_description_is_written_into_the_provenance():
    result = engine.run(two_farms(), {"Fazenda do Seu Zé": SANDY,
                                      "Empresa Jacutinga": CLAYEY},
                        WeightConfig())
    entries = {entry["name"]: entry for entry in result.provenance["sites"]}
    assert set(entries) == {"Fazenda do Seu Zé", "Empresa Jacutinga"}
    assert entries["Empresa Jacutinga"]["factor_classes"]["texture"] == 5
    assert entries["Fazenda do Seu Zé"]["rows"] == 2
    assert "FAZENDA DO SEU ZE" in entries["Fazenda do Seu Zé"]["spellings"]


def test_parameters_are_resolved_once_per_site_and_crop():
    frame = two_farms()
    frame.loc[2:, "crop"] = "Soybean"
    result = engine.run(frame, {"Fazenda do Seu Zé": SANDY,
                                "Empresa Jacutinga": CLAYEY}, WeightConfig())
    assert set(result.parameters) == {
        ("Fazenda do Seu Zé", "Corn, grain"), ("Fazenda do Seu Zé", "Soybean"),
        ("Empresa Jacutinga", "Corn, grain"), ("Empresa Jacutinga", "Soybean"),
    }
    a = result.parameters[("Fazenda do Seu Zé", "Corn, grain")].values["SOC"]
    b = result.parameters[("Empresa Jacutinga", "Corn, grain")].values["SOC"]
    assert a["c"] != b["c"], "different soil, different coefficient"


def test_a_single_site_file_keeps_the_flat_provenance_block():
    """So a report written today can still be compared with an older one."""
    frame = pd.DataFrame([dict(SAMPLE, sample=1)])
    result = engine.run(frame, SANDY, WeightConfig())
    assert result.provenance["factor_classes"]["texture"] == 1
    assert not result.provenance["site_column_used"]
    assert not result.several_sites


def test_per_site_descriptions_survive_a_save_and_reopen(tmp_path):
    project = Project(mapped=two_farms(), per_site=True,
                      site_factors={"Fazenda do Seu Zé": SANDY,
                                    "Empresa Jacutinga": CLAYEY})
    reopened = Project.load(project.save(tmp_path / "p.esmaf"))
    assert reopened.per_site
    assert reopened.factors_for("Empresa Jacutinga").texture == 5
    assert reopened.factors_for("Fazenda do Seu Zé").texture == 1
    assert reopened.factors_complete(reopened.site_index().names)


# ------------------------------------------------- pooling across sites


def test_a_group_mean_names_the_sites_it_pooled():
    """Site is not a grouping key, so a row can average more than one place.

    The comparison this table exists for is between land uses and managements;
    splitting it by site as well would break that comparison into one row per
    farm. What it must not do is average two farms and say nothing.
    """
    frame = pd.concat([two_farms(), two_farms()], ignore_index=True)
    frame["sample"] = range(len(frame))
    result = engine.run(frame, {"Fazenda do Seu Zé": SANDY,
                                "Empresa Jacutinga": CLAYEY}, WeightConfig())
    assert "sites" in result.aggregated.columns
    pooled = result.aggregated["sites"].iloc[0]
    assert "Fazenda do Seu Zé" in pooled and "Empresa Jacutinga" in pooled


def test_one_site_needs_no_such_column():
    frame = two_farms()
    frame["site"] = "Fazenda do Seu Zé"
    result = engine.run(frame, {"Fazenda do Seu Zé": SANDY}, WeightConfig())
    assert "sites" not in result.aggregated.columns


def test_two_farms_numbering_their_replicates_from_one_is_not_a_duplicate():
    """Sample 1 of one farm and sample 1 of another are different samples."""
    rows = [dict(SAMPLE, site=site, sample=n)
            for site in ("Fazenda A", "Fazenda B") for n in (1, 2, 3)]
    report = check(pd.DataFrame(rows), SANDY.as_dict(), WeightConfig(),
                   "esmaf-2.0", units=TEMPLATE_UNITS)
    assert not [f for f in report.warnings if "sample number" in f.what]

    rows.append(dict(SAMPLE, site="Fazenda A", sample=1))
    report = check(pd.DataFrame(rows), SANDY.as_dict(), WeightConfig(),
                   "esmaf-2.0", units=TEMPLATE_UNITS)
    said = [f for f in report.warnings if "sample number" in f.what]
    assert said and "2 rows" in said[0].what
