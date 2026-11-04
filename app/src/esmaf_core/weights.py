"""Weighting schemes for indicators and components.

Two rules govern everything here, and both are departures from the web
version that materially change the numbers:

1. Weights are renormalised over the indicators actually available for a
   given row.  Not measuring an indicator should widen the uncertainty of a
   component, never lower its score.
2. Component weights are renormalised over the components actually
   computable.  A chemical-biological index built from two components must
   still be able to reach 1.00.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .indicators import COMPONENTS, INDICATORS, Component, indicators_for

Scheme = Literal["equal_indicators", "equal_components", "custom"]

SCHEME_LABELS: dict[str, str] = {
    "equal_indicators": "Equal indicator weights",
    "equal_components": "Equal component weights",
    "custom": "Custom weights",
}

SCHEME_EXPLANATIONS: dict[str, str] = {
    "equal_indicators": (
        "Every available indicator contributes equally to the index. Components "
        "therefore carry weight in proportion to how many indicators they "
        "contain, so a component measured with four indicators counts for more "
        "than one measured with two."
    ),
    "equal_components": (
        "The physical, chemical and biological components contribute equally to "
        "the index, and within each component its available indicators "
        "contribute equally. This is the usual choice when the three domains "
        "are considered equally important regardless of how many measurements "
        "back each one."
    ),
    "custom": (
        "You set the weights, in two separate steps. Within each component, the "
        "indicator weights must add up to 100 %: they decide that component's "
        "score, not the index. The component weights, further down, must also "
        "add up to 100 %: they decide the soil health index from the three "
        "component scores. An indicator's share of the index is the product of "
        "the two, so 80 % inside a component that carries 20 % of the index is "
        "16 % of the index."
    ),
}


def _split_hundred(count: int) -> list[float]:
    """Equal shares that add up to exactly 100, to two decimals.

    Three equal parts are 33.3333 each, and three of those add to 99.9999. The
    interface asks the user for 100 and shows them a running total, so the
    values it puts in the boxes had better reach it: the last hundredth goes to
    the first box, giving 33.34, 33.33, 33.33.
    """
    if count <= 0:
        return []
    base = int(10000 / count)               # hundredths of a per cent
    parts = [base] * count
    for i in range(10000 - base * count):
        parts[i] += 1
    return [p / 100 for p in parts]


@dataclass
class WeightConfig:
    """A weighting choice, before it is applied to a particular set of rows."""

    scheme: Scheme = "equal_components"
    #: Only consulted when scheme == "custom". Values are relative, not
    #: required to sum to anything in particular; they are renormalised.
    indicator_weights: dict[str, float] = field(default_factory=dict)
    component_weights: dict[str, float] = field(default_factory=dict)
    #: Indicators the user explicitly excluded from the analysis.
    excluded: set[str] = field(default_factory=set)

    def default_indicator_weights(
            self, available: set[str] | None = None) -> dict[str, float]:
        """Exact equal shares within each component, over what is available.

        Restricted to the indicators in the dataset: five chemical indicators
        given 20 each when only three were measured would leave a component
        that cannot reach 100.
        """
        out: dict[str, float] = {}
        for component in COMPONENTS:
            members = self.members(component, available)
            if members:
                share = 100.0 / len(members)
                for key in members:
                    out[key] = share
        return out

    def default_component_weights(
            self, available: set[str] | None = None) -> dict[str, float]:
        live = [c for c in COMPONENTS if self.members(c, available)] or list(COMPONENTS)
        share = 100.0 / len(live)
        return {c: share for c in live}

    # The two above are exact proportions, used by the equal-weight schemes,
    # where a third has to stay a third. The two below are what the interface
    # puts in the boxes, where the user is asked for 100 and adds the numbers
    # up themselves -- so they are rounded to hundredths that really do total
    # 100 rather than to three thirds that total 99.9999.

    def seed_indicator_weights(
            self, available: set[str] | None = None) -> dict[str, float]:
        out: dict[str, float] = {}
        for component in COMPONENTS:
            members = self.members(component, available)
            if members:
                out.update(zip(members, _split_hundred(len(members))))
        return out

    def seed_component_weights(
            self, available: set[str] | None = None) -> dict[str, float]:
        live = [c for c in COMPONENTS if self.members(c, available)] or list(COMPONENTS)
        return dict(zip(live, _split_hundred(len(live))))

    def effective_indicator_weights(self) -> dict[str, float]:
        if self.scheme == "custom" and self.indicator_weights:
            return dict(self.indicator_weights)
        return self.default_indicator_weights()

    def effective_component_weights(self) -> dict[str, float]:
        if self.scheme == "custom" and self.component_weights:
            return dict(self.component_weights)
        return self.default_component_weights()

    def members(self, component: Component,
                available: set[str] | None = None) -> list[str]:
        """The indicators whose weights the user is being asked to set.

        Only those actually in the dataset. Counting an indicator that was
        never measured would ask for a total the interface gives no box to
        reach: with only bulk density and aggregate stability present, the two
        boxes shown cannot add up to 100 while the two absent indicators still
        carry their defaults.
        """
        return [i.key for i in indicators_for(component)
                if i.key not in self.excluded
                and (available is None or i.key in available)]

    def validate(self, available: set[str] | None = None) -> list[str]:
        """Return human-readable problems; an empty list means the config is usable."""
        problems: list[str] = []
        if self.scheme != "custom":
            return problems
        for component in COMPONENTS:
            keys = self.members(component, available)
            total = sum(self.indicator_weights.get(k, 0.0) for k in keys)
            if keys and abs(total - 100.0) > 0.01 and total != 0:
                problems.append(
                    f"{component.capitalize()} indicator weights add up to "
                    f"{total:.2f} %, not 100 %."
                )
        components = [c for c in COMPONENTS if self.members(c, available)]
        total = sum(self.component_weights.get(c, 0.0) for c in components)
        if len(components) > 1 and abs(total - 100.0) > 0.01 and total != 0:
            problems.append(f"Component weights add up to {total:.2f} %, not 100 %.")
        if any(w < 0 for w in self.indicator_weights.values()) or \
           any(w < 0 for w in self.component_weights.values()):
            problems.append("Weights cannot be negative.")
        return problems


@dataclass(frozen=True)
class AppliedWeights:
    """Weights after renormalisation over what a given row actually has."""

    indicator: dict[str, float]        # sums to 1 within each component
    component: dict[str, float]        # sums to 1 across available components
    available_components: tuple[str, ...]
    missing_indicators: tuple[str, ...]


def apply(config: WeightConfig, available: set[str]) -> AppliedWeights:
    """Renormalise a weight configuration over the indicators present.

    ``available`` holds indicator keys (not score keys); WFPS is expanded into
    its two sub-scores downstream, each taking half of the WFPS weight.
    """
    usable = {k for k in available if k not in config.excluded}
    base_ind = config.effective_indicator_weights()
    base_comp = config.effective_component_weights()

    per_indicator: dict[str, float] = {}
    component_mass: dict[str, float] = {}

    for component in COMPONENTS:
        members = [i.key for i in indicators_for(component) if i.key in usable]
        if not members:
            continue
        if config.scheme == "equal_indicators":
            raw = {k: 1.0 for k in members}
        else:
            raw = {k: float(base_ind.get(k, 0.0)) for k in members}
            if sum(raw.values()) <= 0:
                raw = {k: 1.0 for k in members}
        total = sum(raw.values())
        for key, value in raw.items():
            per_indicator[key] = value / total
        component_mass[component] = total if config.scheme == "equal_indicators" else 1.0

    available_components = tuple(c for c in COMPONENTS if c in component_mass)

    if config.scheme == "equal_indicators":
        # Components inherit weight in proportion to their indicator count.
        total_mass = sum(component_mass.values())
        per_component = {c: component_mass[c] / total_mass for c in available_components}
    else:
        raw_comp = {c: float(base_comp.get(c, 0.0)) for c in available_components}
        if sum(raw_comp.values()) <= 0:
            raw_comp = {c: 1.0 for c in available_components}
        total = sum(raw_comp.values())
        per_component = {c: raw_comp[c] / total for c in available_components}

    missing = tuple(sorted(
        i.key for i in INDICATORS if i.key not in usable
    ))
    return AppliedWeights(
        indicator=per_indicator,
        component=per_component,
        available_components=available_components,
        missing_indicators=missing,
    )


INDEX_NAMES: dict[frozenset[str], str] = {
    frozenset(["physical", "chemical", "biological"]): "Soil Health Index",
    frozenset(["physical", "chemical"]): "Physico-Chemical Quality Index",
    frozenset(["physical", "biological"]): "Physico-Biological Quality Index",
    frozenset(["chemical", "biological"]): "Chemical-Biological Quality Index",
    frozenset(["physical"]): "Physical Quality Index",
    frozenset(["chemical"]): "Chemical Quality Index",
    frozenset(["biological"]): "Biological Quality Index",
}


def index_name(components: tuple[str, ...] | set[str]) -> str:
    return INDEX_NAMES.get(frozenset(components), "Soil Quality Index")


def is_complete(components: tuple[str, ...] | set[str]) -> bool:
    return frozenset(components) == frozenset(COMPONENTS)
