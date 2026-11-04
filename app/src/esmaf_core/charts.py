"""Figures for the interface, the PDF report and image export.

Matplotlib only, so the same code draws the on-screen canvas and the figures
embedded in the report.  Colour carries one meaning throughout: the component
an indicator belongs to.  The palette is fixed and ordered, never cycled.

Every chart states the filter and grouping it is showing in its subtitle. A
chart that does not say what it is comparing is worse than no chart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from .indicators import BY_KEY, COMPONENT_LABELS, COMPONENTS

# --- palette ---------------------------------------------------------------
# Categorical slots 1-3 of a validated palette, assigned to the three
# components. Verified all-pairs for colour-vision deficiency on a light
# surface; the aqua slot sits below 3:1 against the surface, which is why every
# chart here carries direct labels and the application always offers the table.

COMPONENT_COLOR = {
    "physical": "#2a78d6",
    "chemical": "#eb6834",
    "biological": "#1baf7a",
}
INDEX_COLOR = "#4a3aa7"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
INK_FAINT = "#8B9793"
GRID = "#e3e2df"
CURVE = "#256abf"
GROUP_HATCH = ("", "///", "...", "xx")
BAND = "#cde2fb"

plt.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK_SOFT,
    "axes.titlecolor": INK,
    "text.color": INK,
    "xtick.color": INK_SOFT,
    "ytick.color": INK_SOFT,
    "font.size": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
})


@dataclass
class ChartContext:
    """What is being shown, so no figure is ambiguous about its own scope."""

    title: str
    subtitle: str = ""
    footnote: str = ""


def _finish(fig: Figure, ax, context: ChartContext) -> Figure:
    ax.set_axisbelow(True)
    if not ax.get_xgridlines()[0].get_visible():
        ax.grid(axis="x" if ax.get_ylabel() == "" else "y", alpha=0.7)
    fig.suptitle(context.title, x=0.01, ha="left", fontsize=11, fontweight="bold")
    if context.subtitle:
        ax.set_title(context.subtitle, loc="left", fontsize=8.5, color=INK_SOFT, pad=8)
    if context.footnote:
        fig.text(0.01, 0.005, context.footnote, fontsize=7, color=INK_SOFT, ha="left")
    rect = (0, 0.045 if context.footnote else 0, 1, 0.93)
    fig.tight_layout(rect=rect)
    # A Qt canvas resizes the figure to the widget, which invalidates the
    # layout computed here: the label column keeps its fraction of a narrower
    # figure and the longest indicator name is cut off. The rect is kept on the
    # figure so the canvas can lay it out again at its real size.
    fig.esmaf_layout_rect = rect
    return fig


def _component_of(score_column: str) -> str:
    key = score_column.replace("_score", "")
    key = key.split("_")[0] if key.startswith("WFPS") else key
    indicator = BY_KEY.get(key)
    return indicator.component if indicator else "physical"


def _label_of(score_column: str) -> str:
    key = score_column.replace("_score", "")
    if key == "WFPS_BiolAct":
        return "WFPS (biol. activity)"
    if key == "WFPS_EnvProtect":
        return "WFPS (env. protection)"
    indicator = BY_KEY.get(key)
    return indicator.label if indicator else key


def indicator_scores(frame: pd.DataFrame, score_columns: Sequence[str],
                     group_column: str | None, context: ChartContext,
                     figsize: tuple[float, float] | None = None) -> Figure:
    """Horizontal bars, one per indicator, coloured by component.

    Horizontal because indicator names are words, and a reader should not have
    to tilt their head to compare thirteen of them. When several groups are on
    screen they get a panel each rather than interleaved bars: colour is
    already carrying the component, so the group has to be carried by position
    if both are to stay readable.
    """
    labels = [_label_of(c) for c in score_columns]
    y = np.arange(len(score_columns))
    colors = [COMPONENT_COLOR[_component_of(c)] for c in score_columns]

    groups: list = []
    if group_column and group_column in frame.columns:
        groups = list(dict.fromkeys(frame[group_column]))
    panelled = len(groups) > 1

    height = max(3.2, 0.34 * len(score_columns) + 1.5)
    width = figsize[0] if figsize else (
        3.0 + 2.1 * len(groups) if panelled else 8.6)
    fig = Figure(figsize=figsize or (min(13.0, width), height))
    axes = fig.subplots(1, max(1, len(groups)) if panelled else 1,
                        sharey=True, sharex=True)
    axes = np.atleast_1d(axes)

    if panelled:
        for ax, group in zip(axes, groups):
            subset = frame[frame[group_column] == group]
            values = [subset[c].mean() if c in subset else np.nan
                      for c in score_columns]
            ax.barh(y, values, height=0.66, color=colors,
                    edgecolor=SURFACE, linewidth=1.0)
            for yi, value in zip(y, values):
                if np.isfinite(value):
                    ax.text(min(value + 0.03, 1.02), yi, f"{value:.2f}",
                            va="center", fontsize=7.5, color=INK_SOFT)
            ax.set_title(str(group), fontsize=9, color=INK, pad=6)
            ax.set_xlim(0, 1.18)
            ax.set_xticks(np.arange(0, 1.01, 0.25))
            ax.set_axisbelow(True)
            ax.grid(axis="x", alpha=0.7)
    else:
        ax = axes[0]
        values = [frame[c].mean() for c in score_columns]
        ax.barh(y, values, height=0.62, color=colors, edgecolor=SURFACE,
                linewidth=1.0)
        for yi, value in zip(y, values):
            if np.isfinite(value):
                ax.text(min(value + 0.02, 1.03), yi, f"{value:.2f}", va="center",
                        fontsize=8, color=INK_SOFT)
        ax.set_xlim(0, 1.12)
        ax.set_xticks(np.arange(0, 1.01, 0.2))

    axes[0].set_yticks(y, labels, fontsize=8.5)
    axes[0].invert_yaxis()
    fig.supxlabel("Indicator score (0 to 1)", fontsize=9, color=INK_SOFT, y=0.02)
    _legend_components(axes[0], score_columns)

    if panelled:
        # Panel titles already name each group, so the scope line belongs to the
        # figure rather than to the first panel, where it would collide.
        scope = context.subtitle
        if group_column:
            scope = (scope + "  |  " if scope else "") + \
                f"one panel per {group_column.replace('_', ' ')}"
        context = ChartContext(context.title, "", context.footnote)
        fig.text(0.01, 0.925, scope, fontsize=8.5, color=INK_SOFT, ha="left",
                 va="top")
        fig.suptitle(context.title, x=0.01, ha="left", fontsize=11,
                     fontweight="bold")
        if context.footnote:
            fig.text(0.01, 0.005, context.footnote, fontsize=7, color=INK_SOFT,
                     ha="left")
        rect = (0, 0.055 if context.footnote else 0.03, 1, 0.90)
        fig.tight_layout(rect=rect)
        fig.esmaf_layout_rect = rect
        return fig
    return _finish(fig, axes[0], context)


def _legend_components(ax, score_columns: Sequence[str]) -> None:
    present = {_component_of(c) for c in score_columns}
    handles = [Line2D([0], [0], marker="s", linestyle="", markersize=7,
                      markerfacecolor=COMPONENT_COLOR[c], markeredgecolor=SURFACE,
                      label=COMPONENT_LABELS[c])
               for c in COMPONENTS if c in present]
    if len(handles) >= 2:
        ax.figure.legend(handles=handles, frameon=False, fontsize=8, ncols=len(handles),
                         loc="upper right", bbox_to_anchor=(0.99, 0.99))


def component_scores(frame: pd.DataFrame, group_column: str,
                     context: ChartContext, figsize=(8.2, 4.0)) -> Figure:
    """Grouped bars: one cluster per group, one bar per component."""
    fig = Figure(figsize=figsize)
    ax = fig.subplots()
    columns = [f"{c}_component" for c in COMPONENTS if f"{c}_component" in frame.columns]
    groups = list(dict.fromkeys(frame[group_column]))
    x = np.arange(len(groups))
    width = 0.8 / max(1, len(columns))

    for i, column in enumerate(columns):
        component = column.replace("_component", "")
        values = [frame.loc[frame[group_column] == g, column].mean() for g in groups]
        spread = [frame.loc[frame[group_column] == g, column].std() for g in groups]
        offset = (i - (len(columns) - 1) / 2) * width
        ax.bar(x + offset, values, width=width * 0.88,
               color=COMPONENT_COLOR[component], edgecolor=SURFACE, linewidth=1.2,
               label=COMPONENT_LABELS[component])
        ax.errorbar(x + offset, values, yerr=spread, fmt="none",
                    ecolor=INK_SOFT, elinewidth=1.0, capsize=3, alpha=0.55)
        for xi, value in zip(x + offset, values):
            if np.isfinite(value):
                ax.text(xi, value + 0.03, f"{value:.2f}", ha="center",
                        fontsize=7.5, color=INK_SOFT)

    ax.set_xticks(x, [str(g) for g in groups], fontsize=8.5)
    ax.set_ylim(0, 1.12)
    ax.set_yticks(np.arange(0, 1.01, 0.2))
    ax.set_ylabel("Component score (0 to 1)")
    if len(columns) >= 2:
        ax.legend(frameon=False, fontsize=8, ncols=len(columns), loc="upper right")
    return _finish(fig, ax, context)


def index_comparison(frame: pd.DataFrame, index_column: str, group_column: str,
                     index_label: str, complete: bool,
                     context: ChartContext, figsize=(8.2, 4.0)) -> Figure:
    """One bar per group, with the individual samples shown behind it."""
    fig = Figure(figsize=figsize)
    ax = fig.subplots()
    groups = list(dict.fromkeys(frame[group_column]))
    x = np.arange(len(groups))
    means = [frame.loc[frame[group_column] == g, index_column].mean() for g in groups]

    ax.bar(x, means, width=0.5, color=INDEX_COLOR if complete else "#9085e9",
           edgecolor=SURFACE, linewidth=1.2,
           hatch="" if complete else "//")
    for i, group in enumerate(groups):
        points = frame.loc[frame[group_column] == group, index_column].dropna()
        jitter = np.random.default_rng(7).normal(0, 0.045, len(points))
        ax.plot(np.full(len(points), i) + jitter, points, "o", markersize=4,
                markerfacecolor=SURFACE, markeredgecolor=INK_SOFT,
                markeredgewidth=0.9, alpha=0.75, linestyle="")
    for xi, value in zip(x, means):
        if np.isfinite(value):
            ax.text(xi, value + 0.04, f"{value:.2f}", ha="center", fontsize=9,
                    fontweight="bold", color=INK)

    ax.set_xticks(x, [str(g) for g in groups], fontsize=8.5)
    ax.set_ylim(0, 1.15)
    ax.set_yticks(np.arange(0, 1.01, 0.2))
    ax.set_ylabel(f"{index_label} (0 to 1)")
    if not complete:
        ax.text(0.99, 0.02,
                "Hatched: partial index, fewer soil functions than a complete one",
                transform=ax.transAxes, ha="right", fontsize=7.5, color=INK_SOFT)
    return _finish(fig, ax, context)


def scoring_curve(indicator_key: str, curve_x: Sequence[float],
                  curve_y: Sequence[float], sample_x: float, sample_y: float,
                  context: ChartContext, figsize=(5.4, 3.4)) -> Figure:
    """The curve a single measurement was scored against, with the sample on it.

    This is the figure that answers 'why did my sample get that number?', so it
    shows the shape of the function and where the measurement fell on it.
    """
    indicator = BY_KEY.get(indicator_key)
    fig = Figure(figsize=figsize)
    ax = fig.subplots()
    ax.plot(curve_x, curve_y, color=CURVE, linewidth=2.0, solid_capstyle="round")
    ax.fill_between(curve_x, 0, curve_y, color=BAND, alpha=0.35, linewidth=0)

    ax.plot([sample_x], [sample_y], "o", markersize=9, markerfacecolor="#eb6834",
            markeredgecolor=SURFACE, markeredgewidth=2.0, zorder=5)
    ax.annotate(f"{sample_y:.2f}", (sample_x, sample_y),
                textcoords="offset points", xytext=(10, 8),
                fontsize=9, fontweight="bold", color=INK)
    ax.vlines(sample_x, 0, sample_y, color=INK_SOFT, linewidth=1.0,
              linestyle=(0, (3, 3)), alpha=0.6)

    ax.set_ylim(0, 1.08)
    ax.set_yticks(np.arange(0, 1.01, 0.25))
    ax.set_xlabel(f"{indicator.label} ({indicator.unit})" if indicator else indicator_key)
    ax.set_ylabel("Score")
    return _finish(fig, ax, context)


def build_scoring_curve(indicator_key: str, params, model, factors,
                        low: float, high: float, points: int = 220):
    """Sample the scoring function across a range, for the drill-down figure."""
    from . import equations as eq

    xs = np.linspace(low, high, points)
    if indicator_key == "WFPS_BiolAct":
        fn = lambda x: eq.score_wfps_biological(x, **params["WFPS_BiolAct"]).value
    elif indicator_key == "WFPS_EnvProtect":
        fn = lambda x: eq.score_wfps_environmental(x, **params["WFPS_EnvProtect"]).value
    elif indicator_key == "AWC":
        awc = params["AWC"]
        base = eq.score_awc_arid if awc["region"] == "arid" else eq.score_awc_humid
        fn = lambda x: base(x, awc["a"], awc["b"], awc["c"], awc["d"]).value
    else:
        fn = {
            "BD": lambda x: eq.score_bd(x, **params["BD"]).value,
            "AGG": lambda x: eq.score_agg(x, **params["AGG"]).value,
            "pH": lambda x: eq.score_ph(x, **params["pH"]).value,
            "K": lambda x: eq.score_k(x, **params["K"]).value,
            "P": lambda x: eq.score_p(x, **params["P"]).value,
            "SOC": lambda x: eq.score_soc(x, **params["SOC"]).value,
            "MBC": lambda x: eq.score_mbc(x, **params["MBC"]).value,
            "PMN": lambda x: eq.score_pmn(x, **params["PMN"]).value,
            "BG": lambda x: eq.score_bg(x, **params["BG"]).value,
        }[indicator_key]
    return xs, np.array([fn(float(x)) for x in xs])


def weight_tree(indicator_weights: dict[str, float], component_weights: dict[str, float],
                context: ChartContext, figsize=(7.4, 2.9)) -> Figure:
    """One stacked bar, closing at 100 %, of every indicator's share of the index.

    The quantity shown in each segment is the product of the two weights the
    user set: the indicator's share of its component, times that component's
    share of the index. An indicator given 80 % inside a component that carries
    20 % of the index appears here as 16 %, which is the number that actually
    multiplies its score. Reading the two weights separately is what makes a
    custom weighting hard to check; this is the one figure where they are
    already multiplied out.
    """
    fig = Figure(figsize=figsize)
    ax = fig.subplots()

    segments: list[tuple[str, str, float, float]] = []   # component, key, left, width
    spans: list[tuple[str, float, float, float]] = []    # component, left, right, share
    left = 0.0
    for component in COMPONENTS:
        if component not in component_weights:
            continue
        members = [(k, v) for k, v in indicator_weights.items()
                   if BY_KEY[k].component == component]
        if not members:
            continue
        share = component_weights[component]
        start = left
        for key, weight in members:
            width = weight * share
            segments.append((component, key, left, width))
            left += width
        spans.append((component, start, left, share))

    if not segments:
        ax.text(0.5, 0.5, "No weights to show", ha="center", va="center",
                transform=ax.transAxes, color=INK_SOFT)
        ax.set_axis_off()
        return _finish(fig, ax, context)

    # Two rounding passes, components first, so each component shows its own
    # correct share and its indicators add up to exactly that.
    scale = _precision([w for _, _, _, w in segments] +
                       [s for _, _, _, s in spans])
    component_pct = dict(zip(
        [c for c, _, _, _ in spans],
        _largest_remainder([s for _, _, _, s in spans], 100 * scale)))
    segment_pct: dict[str, int] = {}
    for component, *_ in spans:
        members = [(k, w) for c, k, _, w in segments if c == component]
        shares = _largest_remainder([w for _, w in members],
                                    component_pct[component])
        segment_pct.update(dict(zip([k for k, _ in members], shares)))

    def show(value: int) -> str:
        return f"{value / scale:.0f}%" if scale == 1 else f"{value / scale:.1f}%"

    uncounted: list[str] = []
    thin = 0
    for component, key, x, width in segments:
        ax.barh(0, width, left=x, height=0.52,
                color=COMPONENT_COLOR[component], edgecolor=SURFACE, linewidth=1.2,
                zorder=2)
        if segment_pct[key] == 0:
            # Deliberately given no weight. A zero-width sliver cannot carry a
            # label, and two of them side by side print on top of each other,
            # so they are named under the bar instead.
            uncounted.append(key)
            continue
        thin += _segment_label(ax, key, show(segment_pct[key]), x, width, thin)

    # A dark outline around each component's span, so the grouping reads even
    # where two neighbouring segments share a colour.
    for component, start, end, _share in spans:
        ax.add_patch(Rectangle((start, -0.26), end - start, 0.52, fill=False,
                               edgecolor=INK, linewidth=1.1, zorder=3))
        middle = (start + end) / 2
        ax.text(middle, 0.40, COMPONENT_LABELS[component], ha="center", va="bottom",
                fontsize=9, fontweight="bold", color=COMPONENT_COLOR[component],
                clip_on=False)
        ax.text(middle, 0.31, f"{show(component_pct[component])} of the index",
                ha="center", va="bottom", fontsize=7.5, color=INK_SOFT,
                clip_on=False)

    if uncounted:
        ax.text(0, -0.78, "Given no weight: "
                + ", ".join(BY_KEY[k].label.lower() for k in uncounted),
                fontsize=7, color=INK_SOFT, va="top", clip_on=False)

    ax.set_ylim(-0.90 if uncounted else -0.62, 0.72)
    ax.set_yticks([])
    ax.set_xlim(0, 1)
    ax.set_xticks(np.arange(0, 1.01, 0.25),
                  [f"{v:.0%}" for v in np.arange(0, 1.01, 0.25)])
    ax.set_xlabel("Share of the final index")
    ax.spines["left"].set_visible(False)
    ax.grid(axis="x", alpha=0.7)
    return _finish(fig, ax, context)


def _precision(fractions: Sequence[float]) -> int:
    """1 for whole percentages, 10 for one decimal.

    Whole numbers only when they are honest ones. Six equal indicators are
    16.667 % each: printed as integers they come out 17, 17, 17, 17, 16, 16,
    which reads as a mistake rather than as rounding.
    """
    return 1 if all(abs(f * 100 - round(f * 100)) < 0.05 for f in fractions) else 10


def _largest_remainder(fractions: Sequence[float], target: int) -> list[int]:
    """Split ``target`` among ``fractions`` so the parts sum to it exactly.

    Someone reading this figure will add the numbers up, so they have to add
    up. Rounding each part on its own does not: four indicators of 8.33 % print
    as 8 % four times under a component labelled 33 %. The remainder therefore
    goes to the parts that lost the most of it, which is how a percentage table
    is normally made to balance.
    """
    total = sum(fractions)
    if total <= 0:
        return [0] * len(fractions)
    scaled = [f / total * target for f in fractions]
    parts = [int(v) for v in scaled]
    for i in sorted(range(len(scaled)), key=lambda j: scaled[j] - parts[j],
                    reverse=True)[:target - sum(parts)]:
        parts[i] += 1
    return parts


def _segment_label(ax, key: str, value: str, x: float, width: float,
                   staggered: int = 0) -> int:
    """Put the acronym and its share inside the segment, or below a thin one.

    Segments get as narrow as a couple of per cent, so the label shrinks with
    the segment and then moves out of it rather than overflowing into its
    neighbour -- a percentage printed across the wrong colour is worse than one
    printed outside the bar. Returns 1 when it had to go outside, so the caller
    can stagger the next one and keep two thin neighbours from colliding.
    """
    middle = x + width / 2
    room = max(len(key), len(value))        # the wider of the two lines
    # Width needed, as a fraction of the axis: a character of DejaVu Sans Bold
    # is about 0.6 of the font size, the axis is about 430 pt once the figure
    # has been squeezed into a narrow panel, and a fifth is left as padding so
    # a label never touches the segment edge. Measuring the rendered text would
    # be exact, but the Qt canvas rescales the figure afterwards and the
    # measurement would be stale by the time it is drawn.
    for size in (8.5, 7.5, 6.5, 5.6):
        if width >= size * room * 0.00163:
            ax.text(middle, 0.055, key, ha="center", va="center",
                    fontsize=size, fontweight="bold", color="white", zorder=4)
            ax.text(middle, -0.085, value, ha="center", va="center",
                    fontsize=size - 0.5, color="white", zorder=4)
            return 0
    if width >= 0.026:                      # turn it on its side instead
        ax.text(middle, 0, f"{key} {value}", ha="center", va="center",
                fontsize=5.6, fontweight="bold", color="white", zorder=4,
                rotation=90)
        return 0
    depth = -0.40 if staggered % 2 == 0 else -0.50
    ax.annotate(f"{key} {value}", xy=(middle, -0.26), xytext=(middle, depth),
                ha="center", va="top", fontsize=6.5, color=INK_SOFT,
                arrowprops=dict(arrowstyle="-", lw=0.6, color=INK_FAINT),
                annotation_clip=False)
    return 1


def save(fig: Figure, path, dpi: int = 200) -> None:
    fig.savefig(path, dpi=dpi, facecolor=SURFACE, bbox_inches="tight")
    # Nothing to close: the figures are created directly rather than through
    # pyplot, so they are freed with the widget that held them instead of
    # accumulating in pyplot's global registry for the life of the session.
