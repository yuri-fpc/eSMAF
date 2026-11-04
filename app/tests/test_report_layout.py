"""Can the report actually be read?

A result table carries up to twenty-two columns. The first version of the
report divided the page evenly between them, which left every heading and
several of the numbers wrapped across two lines -- "0.9 / 7" is not a number a
reader should have to reassemble. These tests hold the layout to the rule that
replaced it: a column is never narrower than the text it has to print, and a
table that cannot fit is continued below rather than squeezed.
"""

from __future__ import annotations

import pandas as pd
import pytest
from reportlab.lib.units import mm

from esmaf_core import engine, report_pdf as rp
from esmaf_core.parameters import SiteFactors
from esmaf_core.weights import WeightConfig

FACTORS = SiteFactors(region=2, season=1, climate=1, slope=1, texture=4,
                      mineral=3, organic_matter=3, iron_oxide=1, weathering=3,
                      p_method=2, ec_method=1)

SAMPLE = {
    "land_use": "Cropland", "management": "NT", "crop": "Corn, grain",
    "depth": "0-10", "BD": 1.2, "AGG": 70.0, "WFPS": 0.6, "AWC": 0.2,
    "pH": 6.0, "P": 20.0, "K": 300.0, "SAR": 1.0, "EC": 0.4,
    "SOC": 2.5, "PMN": 30.0, "MBC": 800.0, "BG": 300.0,
}

WIDEST = [
    ["Management", "Crop", "Depth", "Sample", "BD", "AGG", "WFPS-b", "WFPS-e",
     "AWC", "pH", "K", "P", "EC", "SAR", "SOC", "MBC", "PMN", "BG", "Phys",
     "Chem", "Biol", "SHI"],
] + [["No-tillage", "Corn, grain", "0-10", f"S{i:03d}"] + ["0.97"] * 18
     for i in range(1, 20)]


def widths_of(table) -> list[float]:
    return list(table._colWidths)


def tables_only(flowables):
    from reportlab.platypus import Table
    return [f for f in flowables if isinstance(f, Table)]


def test_every_column_is_at_least_as_wide_as_its_own_text():
    """The defect that made the first report unreadable."""
    natural = rp._natural_widths(WIDEST)
    tables = tables_only(rp._fitting_tables(WIDEST, rp._styles(), 4,
                                            rp.LANDSCAPE_WIDTH))
    assert len(tables) == 1, "this table does fit on one landscape page"
    for index, width in enumerate(widths_of(tables[0])):
        assert width >= natural[index] - 0.01, (
            f"column {WIDEST[0][index]!r} was laid out at {width:.1f} pt but "
            f"needs {natural[index]:.1f} pt for its own text"
        )


def test_the_measured_width_accounts_for_the_cell_padding():
    """A column has to hold its text *and* the padding either side of it."""
    text_only = rp.stringWidth("Management", rp.CELL_FONT_BOLD, rp.CELL_SIZE)
    measured = rp._natural_widths([["Management"], ["NT"]])[0]
    assert measured >= text_only + 2 * rp.CELL_SIDE_PADDING


def test_a_table_that_cannot_fit_is_split_rather_than_squeezed():
    tables = tables_only(rp._fitting_tables(WIDEST, rp._styles(), 4,
                                            rp.PORTRAIT_WIDTH))
    assert len(tables) > 1, "22 columns cannot fit across a portrait page"
    natural = rp._natural_widths(WIDEST)
    for table in tables:
        assert sum(widths_of(table)) <= rp.PORTRAIT_WIDTH + 0.01
        for width in widths_of(table):
            assert width >= min(natural[4:]) - 0.01


def test_the_identifying_columns_are_repeated_in_every_part():
    tables = tables_only(rp._fitting_tables(WIDEST, rp._styles(), 4,
                                            rp.PORTRAIT_WIDTH))
    for table in tables:
        heading = [cell.text for cell in table._cellvalues[0][:4]]
        assert heading == ["<b>Management</b>", "<b>Crop</b>",
                           "<b>Depth</b>", "<b>Sample</b>"]


def test_a_column_that_never_varies_moves_into_the_caption():
    """Repeating "Cropland" down a hundred rows costs a column and says nothing."""
    rows = [["Land Use", "Management", "Sample", "SHI"]] + \
           [["Cropland", "NT" if i % 2 else "CT", f"S{i}", "0.80"] for i in range(6)]
    trimmed, key_count, moved = rp._drop_constant_keys(rows, 3)
    assert moved == ["Land Use: Cropland"]
    assert key_count == 2
    assert trimmed[0] == ["Management", "Sample", "SHI"]


def test_a_single_row_keeps_all_its_columns():
    """With one row every column is 'constant'; hoisting them would empty the table."""
    rows = [["Land Use", "Sample", "SHI"], ["Cropland", "S1", "0.80"]]
    trimmed, key_count, moved = rp._drop_constant_keys(rows, 2)
    assert moved == []
    assert trimmed == rows and key_count == 2


# ------------------------------------------------------------- end to end


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    frame = pd.DataFrame([dict(SAMPLE, sample=f"S{i:03d}",
                               management="NT" if i % 2 else "CT")
                          for i in range(1, 13)])
    result = engine.run(frame, FACTORS, WeightConfig(scheme="equal_components"))
    path = rp.build(result, tmp_path_factory.mktemp("report") / "r.pdf",
                    rp.ReportOptions(detail="full", project_name="Layout test"))
    return path


def test_the_factor_table_holds_several_sites_without_squeezing_them():
    """One column per site, each at least as wide as the longest class name."""
    from esmaf_core import factors as fx

    names = ["Fazenda do Seu Zé", "Empresa Jacutinga",
             "Estação Experimental de Piracicaba"]
    rows = [["Factor"] + [f"{n} (24)" for n in names]]
    rows += [[factor.label,
              "3 — Autumn - at or just after harvest",
              "2 — Glassy / short-range order",
              "1 — Spring - pre-planting or at planting"]
             for factor in fx.FACTORS]
    natural = rp._natural_widths(rows)
    assert sum(natural) > rp.PORTRAIT_WIDTH, "this is the case that needs the turn"

    tables = tables_only(rp._fitting_tables(rows, rp._styles(), 1,
                                            rp.LANDSCAPE_WIDTH))
    assert len(tables) == 1, "three sites fit across a landscape page"
    for index, width in enumerate(widths_of(tables[0])):
        assert width >= natural[index] - 0.01


def test_the_report_is_produced_and_the_wide_tables_are_landscape(report):
    """Read the page boxes out of the file itself, with no extra dependency."""
    import re

    raw = report.read_bytes()
    boxes = re.findall(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", raw)
    shapes = {("landscape" if float(w) > float(h) else "portrait")
              for w, h in boxes}
    assert shapes == {"portrait", "landscape"}, (
        "the narrative should stay portrait and the result tables should turn"
    )
    assert len(boxes) >= 6
