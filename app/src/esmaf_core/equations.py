"""Scoring equations.

Every function takes one measured value plus the parameters resolved for the
site, and returns a score in [0, 1] together with the information needed to
explain it.  No function reads a global, a DataFrame or a model file: given
the same arguments they always return the same number, which is what makes
the regression tests in ``tests/`` meaningful.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScoreResult:
    """A single indicator score plus the trace behind it."""

    value: float                       # the score, clipped to [0, 1]
    raw: float                         # before clipping, for diagnostics
    equation: str                      # human-readable form of the curve used
    branch: str = ""                   # which limb of a piecewise curve applied
    inputs: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    clipped: bool = False

    def rounded(self, ndigits: int = 2) -> float:
        return round(self.value, ndigits)


def _clip(raw: float) -> tuple[float, bool]:
    if not math.isfinite(raw):
        return 0.0, True
    if raw < 0.0:
        return 0.0, True
    if raw > 1.0:
        return 1.0, True
    return raw, False


def _result(raw: float, equation: str, branch: str = "", **trace) -> ScoreResult:
    value, clipped = _clip(raw)
    return ScoreResult(
        value=value,
        raw=raw,
        equation=equation,
        branch=branch,
        inputs=trace.get("inputs", {}),
        parameters=trace.get("parameters", {}),
        clipped=clipped,
    )


# --------------------------------------------------------------- physical


def score_agg(x: float, a: float, b: float, c: float, d: float,
              saturates_at: float = 50.0) -> ScoreResult:
    """Macroaggregate stability: sinusoidal limit function, y = a + b cos(cx - d).

    Past the saturation point the cosine would turn back down; SMAF holds the
    score at 1 instead, but only once the measurement is strictly above the
    saturation point.  The web version applied the cap at exactly 50 % as
    well, which lifted samples sitting on the boundary from about 0.94 to 1.00.
    """
    raw = a + b * math.cos(c * x - d)
    if x > saturates_at and raw < 1.0:
        return ScoreResult(
            value=1.0, raw=1.0,
            equation="y = 1 (limit branch)",
            branch=f"x > {saturates_at:g} %, curve held at its limit",
            inputs={"AGG": x},
            parameters={"a": a, "b": b, "c": c, "d": d,
                        "saturates_at": saturates_at},
        )
    return _result(
        raw, "y = a + b*cos(c*x - d)", branch=f"x <= {saturates_at:g} %",
        inputs={"AGG": x}, parameters={"a": a, "b": b, "c": c, "d": d},
    )


def score_bd(x: float, a: float, b: float, c: float, d: float) -> ScoreResult:
    """Bulk density: Weibull function, y = a - b exp(-c x^d)."""
    try:
        raw = a - b * math.exp(-c * (x ** d))
    except (OverflowError, ValueError):
        raw = 0.0
    return _result(
        raw, "y = a - b*exp(-c*x^d)",
        inputs={"BD": x}, parameters={"a": a, "b": b, "c": c, "d": d},
    )


def score_wfps_biological(x: float, a: float, b: float, c: float) -> ScoreResult:
    """WFPS, biological activity: quadratic, y = a + bx + cx^2, x as a fraction."""
    raw = a + b * x + c * x * x
    return _result(
        raw, "y = a + b*x + c*x^2",
        inputs={"WFPS": x}, parameters={"a": a, "b": b, "c": c},
    )


def score_wfps_environmental(x: float, a: float, b: float, c: float) -> ScoreResult:
    """WFPS, environmental protection: y = 1 / (a + b x^c), x as a fraction."""
    try:
        denom = a + b * (x ** c)
        raw = 1.0 / denom if denom else 0.0
    except (OverflowError, ValueError, ZeroDivisionError):
        raw = 0.0
    return _result(
        raw, "y = 1 / (a + b*x^c)",
        inputs={"WFPS": x}, parameters={"a": a, "b": b, "c": c},
    )


def score_awc_arid(x: float, a: float, b: float, c: float, d: float) -> ScoreResult:
    """Available water capacity, arid region: Morgan-Mercer-Flodin function."""
    try:
        raw = (a * b + c * (x ** d)) / (b + (x ** d))
    except (OverflowError, ValueError, ZeroDivisionError):
        raw = 0.0
    return _result(
        raw, "y = (a*b + c*x^d) / (b + x^d)", branch="arid region",
        inputs={"AWC": x}, parameters={"a": a, "b": b, "c": c, "d": d},
    )


def score_awc_humid(x: float, a: float, b: float, c: float, d: float) -> ScoreResult:
    """Available water capacity, humid region: sinusoidal function."""
    raw = a + b * math.cos(c * x + d)
    return _result(
        raw, "y = a + b*cos(c*x + d)", branch="humid region",
        inputs={"AWC": x}, parameters={"a": a, "b": b, "c": c, "d": d},
    )


# --------------------------------------------------------------- chemical


def score_ph(x: float, a: float, b: float, c: float) -> ScoreResult:
    """Soil pH: Gaussian centred on the crop optimum, y = a exp(-(x-b)^2 / 2c^2)."""
    if c == 0:
        return _result(0.0, "y = a*exp(-(x-b)^2 / (2c^2))",
                       inputs={"pH": x}, parameters={"a": a, "b": b, "c": c})
    raw = a * math.exp(-((x - b) ** 2) / (2 * c * c))
    return _result(
        raw, "y = a*exp(-(x-b)^2 / (2c^2))",
        inputs={"pH": x}, parameters={"a": a, "b": b, "c": c},
    )


def score_k(x: float, a: float, b: float) -> ScoreResult:
    """Exchangeable potassium: exponential rise, y = a(1 - e^(b x))."""
    try:
        raw = a * (1.0 - math.exp(b * x))
    except OverflowError:
        raw = 0.0
    return _result(
        raw, "y = a*(1 - e^(b*x))",
        inputs={"K": x}, parameters={"a": a, "b": b},
    )


def score_p(x: float, method_factor: float, crop_max: float, crop_fcrop: float,
            sufficiency: dict, environmental: dict,
            b_om: float, b_tx: float, c_om: float, c_tx: float,
            slope_threshold: float, slope_factor: float) -> ScoreResult:
    """Extractable phosphorus: agronomic limb, plateau, environmental limb.

    The measured value is first multiplied by the method factor, which depends
    jointly on the extraction method and the weathering class.  Below the crop
    maximum the score rises with P (agronomic sufficiency); above the
    slope-dependent threshold it falls again (risk of off-site loss); in
    between the soil scores 1.00.
    """
    xm = x * method_factor
    trace = {"P_measured": x, "method_factor": method_factor, "P_adjusted": xm}

    if xm <= crop_max:
        a = sufficiency["a"]
        c = sufficiency["c"]
        d = sufficiency["d"]
        b = crop_fcrop + (crop_fcrop * b_om * b_tx)
        try:
            raw = (a * b + c * (xm ** d)) / (b + (xm ** d))
        except (OverflowError, ValueError, ZeroDivisionError):
            raw = 0.0
        return _result(
            raw, "y = (a*b + c*x^d) / (b + x^d)", branch="agronomic sufficiency",
            inputs=trace,
            parameters={"a": a, "b": b, "c": c, "d": d, "crop_max": crop_max,
                        "b_crop": crop_fcrop, "b_OM": b_om, "b_texture": b_tx},
        )

    if xm > slope_threshold:
        a = environmental["a"]
        b = environmental["b"]
        d = environmental["d"]
        c = (slope_factor + (slope_factor * c_om)) * c_tx
        try:
            raw = a - b * math.exp(-c * (xm ** d))
        except (OverflowError, ValueError):
            raw = 0.0
        return _result(
            raw, "y = a - b*exp(-c*x^d)", branch="environmental loss risk",
            inputs=trace,
            parameters={"a": a, "b": b, "c": c, "d": d,
                        "slope_threshold": slope_threshold,
                        "slope_factor": slope_factor, "c_OM": c_om, "c_texture": c_tx},
        )

    return ScoreResult(
        value=1.0, raw=1.0, equation="y = 1 (sufficiency plateau)",
        branch="between crop maximum and loss-risk threshold",
        inputs=trace,
        parameters={"crop_max": crop_max, "slope_threshold": slope_threshold},
    )


def score_sar(sar: float, ec_saturation: float, table: dict) -> ScoreResult:
    """Sodium adsorption ratio; the branch depends on saturation-paste EC."""
    lo, hi = table["ec_low_threshold"], table["ec_high_threshold"]

    if ec_saturation < lo:
        p = table["low"]
        try:
            raw = 1.0 / (p["a"] + p["b"] * (sar ** p["c"]))
        except (OverflowError, ValueError, ZeroDivisionError):
            raw = 0.0
        branch = f"EC(sat) < {lo:g} dS/m"
        eq = "y = 1 / (a + b*SAR^c)"
        params = dict(p)
    elif ec_saturation < hi:
        p = table["medium"]
        raw = (p["a"] + p["b"] * sar + p["c"] * sar**2 + p["d"] * sar**3
               + p["e"] * sar**4 + p["f"] * sar**5 + p["g"] * sar**6)
        branch = f"{lo:g} <= EC(sat) < {hi:g} dS/m"
        eq = "y = a + b*SAR + c*SAR^2 + ... + g*SAR^6"
        params = dict(p)
    else:
        p = table["high"]
        raw = (p["a"] + p["b"] * sar + p["c"] * sar**2
               + p["d"] * sar**3 + p["e"] * sar**4)
        branch = f"EC(sat) >= {hi:g} dS/m"
        eq = "y = a + b*SAR + c*SAR^2 + d*SAR^3 + e*SAR^4"
        params = dict(p)

    return _result(raw, eq, branch=branch,
                   inputs={"SAR": sar, "EC_saturation_basis": ec_saturation},
                   parameters=params)


def score_ec(x: float, threshold: float, slope: float, intercept: float,
             rise_slope: float, rise_limit: float, basis: str) -> ScoreResult:
    """Electrical conductivity: rising limb, plateau, then linear decline."""
    if x <= rise_limit:
        raw = rise_slope * x
        branch = f"x <= {rise_limit:g} dS/m (rising limb)"
        eq = "y = rise_slope * x"
    elif x < threshold:
        raw = 1.0
        branch = f"{rise_limit:g} < x < T = {threshold:.3g} dS/m (plateau)"
        eq = "y = 1"
    else:
        raw = slope * x + intercept
        branch = f"x >= T = {threshold:.3g} dS/m (salinity decline)"
        eq = "y = m*x + b"
    return _result(
        raw, eq, branch=branch,
        inputs={"EC": x, "basis": basis},
        parameters={"T": threshold, "m": slope, "b": intercept,
                    "rise_slope": rise_slope, "rise_limit": rise_limit},
    )


# ------------------------------------------------------------- biological


def _logistic(x: float, a: float, b: float, c: float, divisor: float = 1.0) -> float:
    try:
        return a / (1.0 + b * math.exp(-c * x / divisor))
    except (OverflowError, ValueError, ZeroDivisionError):
        return 0.0


def score_soc(x: float, a: float, b: float, c: float) -> ScoreResult:
    """Soil organic carbon: logistic, y = a / (1 + b e^(-c x))."""
    return _result(
        _logistic(x, a, b, c), "y = a / (1 + b*e^(-c*x))",
        inputs={"SOC": x}, parameters={"a": a, "b": b, "c": c},
    )


def score_mbc(x: float, a: float, b: float, c: float) -> ScoreResult:
    """Microbial biomass carbon: logistic in mg kg-1."""
    return _result(
        _logistic(x, a, b, c), "y = a / (1 + b*e^(-c*x))",
        inputs={"MBC": x}, parameters={"a": a, "b": b, "c": c},
    )


def score_pmn(x: float, a: float, b: float, c: float) -> ScoreResult:
    """Potentially mineralizable nitrogen: logistic in mg kg-1."""
    return _result(
        _logistic(x, a, b, c), "y = a / (1 + b*e^(-c*x))",
        inputs={"PMN": x}, parameters={"a": a, "b": b, "c": c},
    )


def score_bg(x: float, a: float, b: float, c: float, divisor: float = 1000.0) -> ScoreResult:
    """Beta-glucosidase activity: logistic, with the measurement scaled by 1000."""
    return _result(
        _logistic(x, a, b, c, divisor), "y = a / (1 + b*e^(-c*x/1000))",
        inputs={"BG": x}, parameters={"a": a, "b": b, "c": c, "divisor": divisor},
    )
