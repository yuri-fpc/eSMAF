# eSMAF

**Electronic Soil Management Assessment Framework** — a desktop application
that turns soil measurements into soil health scores using the Soil Management
Assessment Framework (SMAF), and records enough about each analysis that the
result can be reproduced later.

SMAF converts 13 physical, chemical and biological indicators into scores
between 0 and 1, aggregates them into three components, and combines those into
a Soil Health Index. eSMAF implements that method as versioned, tested software
instead of a spreadsheet, so that a published score can be traced to the exact
equations, parameters and analytical conventions that produced it.

Everything runs on your own computer. No account, no upload, no row limit, and
no measurement leaves the machine.

---

## Download

Ready-to-run builds are attached to each
[release](https://github.com/yuri-fpc/eSMAF/releases). Download the folder
for your system, unzip it anywhere, and run `eSMAF.exe`. There is no installer
and nothing is written outside the folder you choose.

`eSMAF.exe --selftest` scores a reference sample and checks 16 values before you
trust it with your own data.

## Running from source

```bash
python3.11 -m venv .venv
source .venv/bin/activate        # .\.venv\Scripts\Activate.ps1 on Windows
pip install -r app/requirements.txt
python app/run_esmaf.py
```

To build the packaged application yourself: `python app/build.py`
(or `app\build_windows.bat` on Windows). The build checks every source file
against `app/MANIFEST.sha256` before it starts, so a packaged build always
corresponds to a known source tree.

## How an analysis goes

The application is six steps, in order, and tells you at every point what is
done and what is still missing.

1. **Data** — drop in an Excel or CSV file. Columns are matched against the
   known indicator names; anything unmatched is reported with the closest
   candidates rather than silently dropped.
2. **Units** — every indicator states the unit it was measured in. eSMAF reads
   the unit from the column header where the header gives one, proposes but
   never assumes where it does not, and refuses to score until the question is
   answered. Presets cover whole laboratory systems.
3. **Setup** — the eleven factor classes that adapt the scoring curves to the
   site, plus the crop, the management and the weighting scheme. Nothing carries
   a default: a default here would be a scientific decision taken on your behalf.
4. **Analysis check** — what will be calculated and what deserves attention,
   with errors that block the calculation kept separate from warnings that
   do not.
5. **Results** — one score per sample or group means, charts, and a drill-down
   that opens any score to show the value supplied, the conversion, the curve
   with the sample on it, the factor classes that shaped it, the resolved
   coefficients and the contribution to the index.
6. **Report and export** — Excel workbook, PDF report at three levels of detail,
   CSV, chart images, and a `.esmaf` project file that reopens the study exactly
   where you left it.

Several sites can live in one dataset. Add a `site` column and eSMAF asks
whether those places share one description or are characterised separately.

## What is in this repository

```
app/
  src/esmaf_core/     the scientific core: equations, parameters, units,
                      validation, weighting, aggregation, exports
  src/esmaf_app/      the desktop interface (PySide6/Qt)
  tests/              the test suite, including the reference datasets
  build.py            packaging, with a source-integrity check
  MANIFEST.sha256     the checksum of every file a build is made from
verification/         reproduces the published assessment of Section 3.3
docs/
  SUP-1 … Factor Classes   what each factor class means and how to choose it
  SUP-2 … Crop Guide       the crop database and its parameters
  SUP-3 … Guide            step by step, from spreadsheet to report
```

The core knows nothing about the interface. That separation is what allows the
equations to be tested on their own, and is enforced by the tests.

## Tests

```bash
cd app && python -m pytest tests -q
```

218 tests. They cover the scoring equations against 531 values printed by the
example-curve tables of the original SMAF workbook, reproduced to within 0.001;
the unit conversions, including a real Brazilian laboratory report; the
weighting arithmetic at both levels; site-name reconciliation; and the report
and workbook layouts.

A third set reproduces a published field assessment:

```bash
cd verification
python run_verification.py     # scores the dataset and writes the comparisons
python decompose.py            # separates the parameter differences
python check_numbers.py        # asserts every number quoted in the article
```

`cherubin2016.py` is the transcription of Tables 2 and 3 of Cherubin et al.
(2016) together with the factor classes that study reports; the scripts score
it with eSMAF and compare. All three sets run automatically before a release is
packaged, so a change that alters a reference score cannot ship unnoticed.

## Guides

`docs/` holds the three guides that accompany the article: what each factor
class means and how to choose it, the crop database and its parameters, and a
step-by-step walk from spreadsheet to report.

## Versions and provenance

Every analysis records the software version, the calculation model, the crop
database version, the declared units and the factor classes of each site. This
is what allows two assessments to be compared: a difference between them can be
attributed to a specific decision rather than left unexplained.

| | |
|---|---|
| Software | 2.0.0 |
| Calculation model | `esmaf-2.0` — original SMAF with Brazilian adaptations |
| Crop database | 2025.1 |
| Project format | 1 |

Adding a crop or a locally calibrated parameter set means adding a data file,
not editing the equations, so results published under an earlier model stay
reproducible.

## Licence

PolyForm Noncommercial 1.0.0, plus a condition on the name. You may use, study,
modify and redistribute eSMAF for any noncommercial purpose; a modified version
must not be presented as eSMAF. See [LICENSE.md](LICENSE.md). For commercial
use, write to the address below.

## Citing eSMAF

If eSMAF contributed to work you publish, please cite both the software and the
article. GitHub's "Cite this repository" button reads `CITATION.cff`, and each
release has its own DOI on Zenodo, so you can cite the exact version you ran.

> Castilho, Y.P. & Sibulski, M. (2026). *eSMAF: Electronic Soil Management
> Assessment Framework* (version 2.0.0) [Computer software].
> https://doi.org/10.5281/zenodo.23965940

## Contact

Yuri Parra Castilho — yuri.castilho@usp.br
Department of Soil Science, Luiz de Queiroz College of Agriculture,
University of São Paulo, Piracicaba, Brazil

Requests to add a crop to the database are welcome. Salinity thresholds for the
Brazilian crop entries are the current priority, and electrical conductivity and
sodium adsorption ratio cannot be scored for them until those are available.
