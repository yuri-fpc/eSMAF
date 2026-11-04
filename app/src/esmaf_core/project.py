"""The ``.esmaf`` project file.

A project is a single zip container holding the raw data exactly as imported,
the column mapping, the factor classes, the weights and a history of the
analyses that were run.  Reopening it restores the state the user left, and
re-running it reproduces the numbers -- which is the whole point of recording
the model and database versions alongside them.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from . import units as un
from . import version as ver
from .parameters import SiteFactors
from .weights import WeightConfig

SUFFIX = ".esmaf"
_RAW = "data/raw.csv"
_MAPPED = "data/mapped.csv"
_META = "project.json"
_HISTORY = "history.json"


@dataclass
class AnalysisRecord:
    """One entry in the project's history."""

    timestamp: str
    label: str
    provenance: dict[str, Any]
    summary: str = ""
    n_samples: int = 0


@dataclass
class Project:
    name: str = "Untitled project"
    description: str = ""
    created: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))
    modified: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))

    raw: pd.DataFrame | None = None          # exactly as imported, never edited
    mapped: pd.DataFrame | None = None       # canonical column names, converted
    column_mapping: dict[str, str | None] = field(default_factory=dict)
    #: Indicator key -> declared unit. The one property of the data that
    #: cannot be read from the data, so it is asked for and then travels with
    #: the project rather than being guessed at on every import.
    units: dict[str, str] = field(default_factory=dict)
    #: The preset the user picked, if any. Kept because two presets can ask for
    #: the same units and the selector must still show the one that was chosen.
    unit_preset: str | None = None
    source_file: str = ""
    source_sheet: str = ""

    #: How the site was described. ``factors`` is the shared description, used
    #: when every place in the file has the same soil, climate and methods.
    #: ``per_site`` switches to ``site_factors``, one description per site --
    #: which is what lets one spreadsheet hold several farms without scoring
    #: any of them against another's curves.
    factors: SiteFactors = field(default_factory=SiteFactors)
    #: None until the question has been answered. With several sites in the
    #: file neither answer may be assumed: "they are the same soil" is a
    #: scientific claim, and "they are different" would make a single-farm user
    #: describe one place several times.
    per_site: bool | None = None
    site_factors: dict[str, SiteFactors] = field(default_factory=dict)
    #: Site names the user has confirmed mean one place. Stored so the
    #: decision travels with the project instead of being made again.
    site_merges: list[list[str]] = field(default_factory=list)
    #: How the density that converts a per-volume result to a mass basis is
    #: obtained. Only consulted when some column was declared per volume.
    density_rule: str = un.DEFAULT_DENSITY_RULE
    weights: WeightConfig = field(default_factory=WeightConfig)
    model_id: str = ver.DEFAULT_MODEL_ID

    history: list[AnalysisRecord] = field(default_factory=list)
    path: Path | None = None

    # -------------------------------------------------------------- state

    @property
    def has_data(self) -> bool:
        return self.mapped is not None and not self.mapped.empty

    # ------------------------------------------------------------- sites

    def site_index(self):
        """The sites in the imported data, with the confirmed merges applied."""
        from . import sites as st

        column = (self.mapped["site"]
                  if self.has_data and "site" in self.mapped.columns else None)
        return st.build(column, self.site_merges)

    def site_question_open(self) -> bool:
        """Several sites in the file and no answer yet about their soils."""
        index = self.site_index()
        return index.from_column and index.several and self.per_site is None

    # ------------------------------------------------------------- units

    def declare_units(self, proposed: dict) -> None:
        """Take the units the headers stated; leave the rest to be asked."""
        for key, unit_id in proposed.items():
            if unit_id:
                self.units[key] = unit_id

    def available_indicators(self) -> set[str]:
        """Indicator keys this dataset actually holds a column for."""
        if not self.has_data:
            return set()
        from .indicators import INDICATORS

        return {i.key for i in INDICATORS if i.key in self.mapped.columns}

    def units_missing(self) -> list[str]:
        if not self.has_data:
            return []
        from .indicators import INDICATORS

        return [i.key for i in INDICATORS
                if i.key in self.mapped.columns and un.must_be_declared(i.key)
                and not self.units.get(i.key)]

    def uses_volume_basis(self) -> bool:
        return bool(un.needs_density(self.units))

    def factors_for(self, site: str) -> SiteFactors:
        if not self.per_site:
            return self.factors
        return self.site_factors.get(site, SiteFactors())

    def factors_argument(self, names: Sequence[str]):
        """What to hand the engine: one description, or one per site."""
        if not self.per_site:
            return self.factors
        return {name: self.factors_for(name) for name in names}

    def selections(self, names: Sequence[str]) -> dict[str, dict]:
        """Per-site factor selections in the plain-dict form the check uses."""
        return {name: self.factors_for(name).as_dict() for name in names}

    def missing_by_site(self, names: Sequence[str]) -> dict[str, list[str]]:
        return {name: self.factors_for(name).missing for name in names}

    def factors_complete(self, names: Sequence[str]) -> bool:
        if not self.per_site:
            return self.factors.complete
        return bool(names) and all(self.factors_for(n).complete for n in names)

    def progress(self) -> list[tuple[str, bool, str]]:
        """The checklist the interface shows: (step, done, detail).

        Factor classes count as done only when every one of them has been
        chosen.  Counting only the classes the present indicators happen to
        need would let a project look finished and then change its scores the
        moment another indicator arrives in the next import.
        """
        from .factors import FACTORS

        indicators = []
        if self.has_data:
            from .indicators import INDICATORS
            indicators = [i.key for i in INDICATORS if i.key in self.mapped.columns]

        names = self.site_index().names if self.has_data else []
        per = len(FACTORS)
        if self.per_site and names:
            total = per * len(names)
            chosen = total - sum(len(self.factors_for(n).missing) for n in names)
            unfinished = [n for n in names if not self.factors_for(n).complete]
            detail_suffix = (
                f" — still to describe: {', '.join(unfinished[:3])}"
                + (" …" if len(unfinished) > 3 else "")) if unfinished else ""
        else:
            total, chosen = per, per - len(self.factors.missing)
            missing = self.factors.missing
            detail_suffix = (
                " — still to choose: "
                + ", ".join(k.replace("_", " ") for k in missing[:4])
                + (" …" if len(missing) > 4 else "")) if missing else ""
        complete = self.factors_complete(names) and not self.site_question_open()
        weight_problems = self.weights.validate(self.available_indicators())
        needed = [k for k in indicators if un.must_be_declared(k)]
        declared = [k for k in needed if self.units.get(k)]
        return [
            ("Data imported", self.has_data,
             f"{len(self.mapped)} rows" if self.has_data else "no data yet"),
            ("Indicators recognised", bool(indicators),
             f"{len(indicators)} indicator(s)" if indicators else "none"),
            ("Units stated", bool(needed) and len(declared) == len(needed),
             f"{len(declared)} of {len(needed)}" if needed else "-"),
            ("Factor classes chosen", complete,
             f"{chosen} of {total}"
             + (f" (across {len(names)} sites)" if self.per_site and len(names) > 1
                else "")
             + detail_suffix),
            ("Weights valid", not weight_problems,
             "; ".join(weight_problems) or
             {"equal_indicators": "Equal indicator weights",
              "equal_components": "Equal component weights",
              "custom": "Custom weights"}[self.weights.scheme]),
            ("Results available", bool(self.history),
             f"{len(self.history)} analysis run(s)" if self.history else "not calculated yet"),
        ]

    def ready(self) -> bool:
        steps = self.progress()
        return all(done for _, done, _ in steps[:5])

    def record(self, label: str, provenance: dict[str, Any], summary: str,
               n_samples: int) -> None:
        self.history.append(AnalysisRecord(
            timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
            label=label, provenance=provenance, summary=summary, n_samples=n_samples,
        ))
        self.touch()

    def touch(self) -> None:
        self.modified = datetime.now().astimezone().isoformat(timespec="seconds")

    # ---------------------------------------------------------- save/load

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path or self.path or f"{self.name}{SUFFIX}")
        if target.suffix != SUFFIX:
            target = target.with_suffix(SUFFIX)
        self.touch()
        meta = {
            "format_version": ver.PROJECT_FORMAT_VERSION,
            "written_by": ver.SOFTWARE_VERSION,
            "name": self.name,
            "description": self.description,
            "created": self.created,
            "modified": self.modified,
            "source_file": self.source_file,
            "source_sheet": self.source_sheet,
            "column_mapping": self.column_mapping,
            "units": dict(self.units),
            "unit_preset": self.unit_preset,
            "density_rule": self.density_rule,
            "factors": self.factors.as_dict(),
            "per_site": self.per_site,
            "site_factors": {name: value.as_dict()
                             for name, value in self.site_factors.items()},
            "site_merges": [list(group) for group in self.site_merges],
            "model_id": self.model_id,
            "weights": {
                "scheme": self.weights.scheme,
                "indicator_weights": self.weights.indicator_weights,
                "component_weights": self.weights.component_weights,
                "excluded": sorted(self.weights.excluded),
            },
        }
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(_META, json.dumps(meta, indent=2, ensure_ascii=False))
            archive.writestr(_HISTORY, json.dumps(
                [asdict(record) for record in self.history], indent=2, ensure_ascii=False))
            if self.raw is not None:
                archive.writestr(_RAW, self.raw.to_csv(index=False))
            if self.mapped is not None:
                archive.writestr(_MAPPED, self.mapped.to_csv(index=False))
        self.path = target
        return target

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        path = Path(path)
        with zipfile.ZipFile(path) as archive:
            meta = json.loads(archive.read(_META).decode("utf-8"))
            stored_format = meta.get("format_version", 0)
            if stored_format > ver.PROJECT_FORMAT_VERSION:
                raise ProjectVersionError(
                    f"'{path.name}' was written by eSMAF "
                    f"{meta.get('written_by', 'a newer version')} and uses project "
                    f"format {stored_format}; this build reads up to format "
                    f"{ver.PROJECT_FORMAT_VERSION}. Update eSMAF to open it."
                )
            raw = _read(archive, _RAW)
            mapped = _read(archive, _MAPPED)
            history = [AnalysisRecord(**record)
                       for record in json.loads(archive.read(_HISTORY).decode("utf-8"))] \
                if _HISTORY in archive.namelist() else []

        weights_meta = meta.get("weights", {})
        project = cls(
            name=meta.get("name", path.stem),
            description=meta.get("description", ""),
            created=meta.get("created", ""),
            modified=meta.get("modified", ""),
            raw=raw,
            mapped=mapped,
            column_mapping=meta.get("column_mapping", {}),
            units=dict(meta.get("units", {})),
            unit_preset=meta.get("unit_preset"),
            density_rule=meta.get("density_rule", un.DEFAULT_DENSITY_RULE),
            source_file=meta.get("source_file", ""),
            source_sheet=meta.get("source_sheet", ""),
            factors=_factors(meta.get("factors", {})),
            per_site=meta.get("per_site", None),
            site_factors={name: _factors(value)
                          for name, value in meta.get("site_factors", {}).items()},
            site_merges=[list(group) for group in meta.get("site_merges", [])],
            weights=WeightConfig(
                scheme=weights_meta.get("scheme", "equal_components"),
                indicator_weights=weights_meta.get("indicator_weights", {}),
                component_weights=weights_meta.get("component_weights", {}),
                excluded=set(weights_meta.get("excluded", [])),
            ),
            model_id=meta.get("model_id", ver.DEFAULT_MODEL_ID),
            history=history,
            path=path,
        )
        return project


def _factors(stored: dict) -> SiteFactors:
    """Tolerant of a project written by another version of the format."""
    return SiteFactors(**{k: v for k, v in (stored or {}).items()
                          if k in SiteFactors.__dataclass_fields__})


def _read(archive: zipfile.ZipFile, name: str) -> pd.DataFrame | None:
    """One stored table, or None when the container does not carry it.

    A frame with no columns writes as an empty CSV, which pandas then refuses
    to read back. That happens for real: a file that turns out to hold nothing
    eSMAF can use leaves an empty table behind, and the project would not open
    again afterwards. An empty member reads as an empty frame.
    """
    if name not in archive.namelist():
        return None
    import io

    payload = archive.read(name)
    if not payload.strip():
        return pd.DataFrame()
    try:
        return pd.read_csv(io.BytesIO(payload))
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


class ProjectVersionError(ValueError):
    """Raised when a project file is newer than this build can read."""
