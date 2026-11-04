"""Calculation models: versioned bundles of parameters and switches.

A model is data, not code.  Adding a crop, retuning a factor table or
correcting a coefficient means editing JSON and bumping an identifier, and
every result records which model produced it.  That is what makes the
question "why is today's number different from the one I got two years ago?"
answerable.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
MODEL_DIR = DATA_DIR / "models"


@dataclass(frozen=True)
class Model:
    id: str
    label: str
    summary: str
    texture_classes: int
    tables: dict[str, Any]
    switches: dict[str, Any]
    departures: list[dict[str, str]] = field(default_factory=list)
    known_defects: list[str] = field(default_factory=list)
    deprecated: bool = False
    based_on: str = ""

    def table(self, key: str) -> dict[str, Any]:
        try:
            return self.tables[key]
        except KeyError as exc:  # pragma: no cover - configuration error
            raise KeyError(
                f"Model '{self.id}' has no parameter table for '{key}'. "
                f"Available: {sorted(self.tables)}"
            ) from exc

    def switch(self, key: str, default: Any = None) -> Any:
        return self.switches.get(key, default)


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


@lru_cache(maxsize=None)
def load_model(model_id: str) -> Model:
    """Load a model by identifier, resolving inheritance."""
    path = MODEL_DIR / f"{model_id}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Unknown calculation model '{model_id}'. "
            f"Available: {', '.join(available_models())}"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))

    if parent_id := raw.get("derives_from"):
        parent = load_model(parent_id)
        tables = _deep_merge(parent.tables, raw.get("overrides", {}).get("tables", {}))
        switches = _deep_merge(parent.switches, raw.get("switches", {}))
        departures = parent.departures + raw.get("departures", [])
        texture_classes = raw.get("texture_classes", parent.texture_classes)
        based_on = raw.get("based_on", parent.based_on)
    else:
        tables = raw.get("tables", {})
        switches = raw.get("switches", {})
        departures = raw.get("departures", [])
        texture_classes = raw.get("texture_classes", 5)
        based_on = raw.get("based_on", "")

    return Model(
        id=raw["id"],
        label=raw.get("label", raw["id"]),
        summary=raw.get("summary", ""),
        texture_classes=texture_classes,
        tables=_numeric_keys(tables),
        switches=switches,
        departures=departures,
        known_defects=raw.get("known_defects", []),
        deprecated=bool(raw.get("deprecated", False)),
        based_on=based_on,
    )


def available_models() -> list[str]:
    return sorted(p.stem for p in MODEL_DIR.glob("*.json"))


def _numeric_keys(obj: Any) -> Any:
    """JSON keys are strings; the factor tables are indexed by class code.

    Class codes are kept as strings throughout the engine so that the combined
    season x climate codes ("2.1", "3.4") and the plain integer codes ("1")
    can live in the same table without floating-point key collisions -- the
    defect that made ``ENV['P_method'] + ENV['Weathering_class']/10`` fragile
    in the web version.
    """
    if isinstance(obj, dict):
        return {str(k): _numeric_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_numeric_keys(v) for v in obj]
    return obj
