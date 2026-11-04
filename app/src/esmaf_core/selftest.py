"""Does this build still compute what it is supposed to compute?

The test suite under ``tests/`` needs the source tree and pytest. A packaged
build has neither, so it carries this instead: one reference sample with its
expected scores, checked against the engine as it was actually frozen. It
verifies the parts of packaging that silently go wrong -- the crop database and
the model files being found, the parameter tables being complete -- and it
verifies that the arithmetic did not move.

Run it from a source checkout with ``python run_esmaf.py --selftest``, or from
a packaged build with ``eSMAF.exe --selftest``.
"""

from __future__ import annotations

import sys

#: One clayey Oxisol under green-harvest sugarcane, the case used throughout
#: the audit. Chosen because it exercises texture class 5, the resin P method
#: factor, a crop with no salinity threshold, and both WFPS sub-scores.
REFERENCE_SAMPLE = {
    "land_use": "Cropland",
    "management": "NT",
    "crop": "Brazilian sugarcane",
    "depth": "0-10",
    "BD": 1.30,
    "AGG": 85.0,
    "WFPS": 0.55,
    "AWC": 0.18,
    "pH": 5.2,
    "P": 18.0,
    "K": 180.0,
    "SOC": 1.8,
    "PMN": 22.0,
    "MBC": 350.0,
    "BG": 180.0,
}

REFERENCE_FACTORS = {
    "region": 2, "season": 3, "climate": 1, "slope": 2, "texture": 5,
    "mineral": 3, "organic_matter": 3, "iron_oxide": 2, "weathering": 2,
    "p_method": 5, "ec_method": 2,
}

EXPECTED = {
    "AGG_score": 1.00,
    "AWC_score": 0.84,
    "BD_score": 0.57,
    "BG_score": 0.25,
    "K_score": 1.00,
    "MBC_score": 0.91,
    "PMN_score": 1.00,
    "P_score": 1.00,
    "SOC_score": 0.64,
    "WFPS_BiolAct_score": 0.95,
    "WFPS_EnvProtect_score": 0.95,
    "pH_score": 0.73,
    "physical_component": 0.84,
    "chemical_component": 0.91,
    "biological_component": 0.70,
    "soil_health_index": 0.82,
}

TOLERANCE = 0.005


def run(verbose: bool = True) -> int:
    """Return 0 if this build is sound, 1 otherwise."""
    problems: list[str] = []

    def report(line: str) -> None:
        if verbose:
            print(line)

    import pandas as pd

    from . import version as ver
    from .crops import load_crops
    from .engine import AnalysisOptions, run as run_analysis
    from .indicators import INDICATORS
    from .models import available_models, load_model
    from .parameters import SiteFactors
    from .weights import WeightConfig

    report(f"eSMAF {ver.SOFTWARE_VERSION} self-test")
    report(f"  python              {sys.version.split()[0]}")
    report(f"  frozen build        {'yes' if getattr(sys, 'frozen', False) else 'no'}")

    # --- the data files have to be reachable -----------------------------
    models = available_models()
    report(f"  calculation models  {', '.join(models) or 'NONE FOUND'}")
    if ver.DEFAULT_MODEL_ID not in models:
        problems.append(
            f"the default model '{ver.DEFAULT_MODEL_ID}' was not found; the "
            "model files did not make it into this build"
        )

    crops = load_crops()
    report(f"  crops in database   {len(crops)}")
    if len(crops) < 100:
        problems.append(
            f"only {len(crops)} crops loaded; the crop database is missing or truncated"
        )

    # --- every factor class in the model has to resolve ------------------
    if ver.DEFAULT_MODEL_ID in models:
        model = load_model(ver.DEFAULT_MODEL_ID)
        report(f"  texture classes     {model.texture_classes}")
        if model.texture_classes != 5:
            problems.append(
                f"the default model offers {model.texture_classes} texture "
                "classes; SMAF defines five"
            )
        missing = [i.key for i in INDICATORS if i.key not in model.tables]
        if missing:
            problems.append(
                "the model has no parameter table for: " + ", ".join(missing)
            )

    if problems:
        _print_problems(problems, verbose)
        return 1

    # --- and the arithmetic has to be unchanged --------------------------
    frame = pd.DataFrame([REFERENCE_SAMPLE])
    factors = SiteFactors(**REFERENCE_FACTORS)
    result = run_analysis(
        frame, factors, WeightConfig(scheme="equal_components"),
        AnalysisOptions(model_id=ver.DEFAULT_MODEL_ID),
    )
    row = result.scores.iloc[0]

    report("  reference sample    clayey Oxisol, sugarcane, texture class 5")
    checked = 0
    for column, expected in EXPECTED.items():
        if column not in result.scores.columns:
            problems.append(f"{column} was not produced at all")
            continue
        got = float(row[column])
        checked += 1
        if abs(got - expected) > TOLERANCE:
            problems.append(
                f"{column}: this build gives {got:.3f}, the reference is {expected:.2f}"
            )
    report(f"  values checked      {checked} of {len(EXPECTED)}")

    if not problems:
        report(f"  soil health index   {row['soil_health_index']:.2f} as expected")
        report("")
        report("PASS - this build reproduces the reference scores.")
        return 0

    _print_problems(problems, verbose)
    return 1


def _print_problems(problems: list[str], verbose: bool) -> None:
    if not verbose:
        return
    print("")
    print(f"FAIL - {len(problems)} problem(s):")
    for problem in problems:
        print(f"  - {problem}")
    print("")
    print("This build should not be used for analysis. Rebuild it, and if the")
    print("problem persists send build_log.txt.")


if __name__ == "__main__":
    raise SystemExit(run())
