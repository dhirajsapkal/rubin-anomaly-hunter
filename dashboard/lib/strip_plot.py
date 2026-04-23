"""Tiny horizontal strip-plot SVG for entry-level evidence rows.

Draws a population of values as small grey tick-marks on a thin rail and
marks a single flagged value with an amber upward triangle. Intended for
inline use beside an evidence label like "e", "|A1|", or "fit_rms" so the
reader sees at-a-glance whether the flagged value is an outlier.

Deterministic, pure-data, transparent background. No title — the label is
baked into the SVG as a tiny rail-end annotation only when there is no
population to compare against.
"""

from __future__ import annotations

import io

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _HAS_MPL = True
except Exception:
    _HAS_MPL = False


_POP_TICK = "#5B6275"
_RAIL = "#252C3C"
_FLAG = "#FFB020"
_TEXT_MUTED = "#5B6275"


def _empty_svg(message: str, width: float, height: float) -> str:
    w, h = int(width * 72), int(height * 72)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}">'
        f'<text x="{w//2}" y="{h//2}" text-anchor="middle" '
        f'dominant-baseline="middle" font-family="IBM Plex Mono, monospace" '
        f'font-style="italic" font-size="10" fill="#5B6275">{message}</text>'
        f'</svg>'
    )


def _fmt(v: float) -> str:
    """Compact numeric formatting: 3 sig figs unless integer-ish."""
    if v is None:
        return "—"
    av = abs(v)
    if av == 0:
        return "0"
    if av >= 100:
        return f"{v:.0f}"
    if av >= 10:
        return f"{v:.1f}"
    if av >= 1:
        return f"{v:.2f}"
    return f"{v:.3f}"


def strip_plot_svg(
    values: list[float],
    flagged_value: float | None,
    label: str,
    width: float = 3.0,
    height: float = 0.45,
) -> str:
    """Render a horizontal strip-plot.

    Parameters
    ----------
    values:
        Population to plot as grey ticks. May be empty.
    flagged_value:
        The inspected entry's value. Drawn as an amber upward triangle
        above the rail. May be ``None`` if only the population is shown.
    label:
        Short evidence name ("e", "|A1|", "fit_rms"). Only rendered when
        ``values`` is empty but ``flagged_value`` is present, as a hint.
    width, height:
        Matplotlib figsize in inches. Height intentionally ~32–40 px.
    """
    if not _HAS_MPL:
        return _empty_svg("—", width, height)

    has_pop = bool(values)
    has_flag = flagged_value is not None

    if not has_pop and not has_flag:
        return _empty_svg("no data", width, height)

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor("none")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    # Determine axis range.
    pool: list[float] = []
    if has_pop:
        pool.extend(float(v) for v in values)
    if has_flag:
        pool.append(float(flagged_value))  # type: ignore[arg-type]
    lo = min(pool)
    hi = max(pool)
    if hi == lo:
        # Expand a little so the marker doesn't sit flush.
        pad = max(abs(lo) * 0.1, 0.01)
        lo -= pad
        hi += pad
    span = hi - lo
    # Add a small horizontal margin so markers don't clip the edge.
    margin = span * 0.04
    ax.set_xlim(lo - margin, hi + margin)
    ax.set_ylim(-1.0, 1.0)

    # Rail
    ax.plot([lo, hi], [0, 0], color=_RAIL, linewidth=1.1, zorder=1,
            solid_capstyle="butt")

    # Population ticks — vertical bars crossing the rail.
    if has_pop:
        for v in values:
            try:
                xv = float(v)
            except (TypeError, ValueError):
                continue
            ax.plot(
                [xv, xv], [-0.35, 0.35],
                color=_POP_TICK, linewidth=1.0, alpha=0.75, zorder=2,
            )

    # Flagged marker — amber upward triangle sitting just above the rail.
    if has_flag:
        fv = float(flagged_value)  # type: ignore[arg-type]
        ax.scatter(
            [fv], [0.55],
            marker="^", s=44, color=_FLAG,
            edgecolors="#070A10", linewidths=0.6, zorder=5,
        )

    # End-cap labels: min on the left, max on the right. Tiny & muted.
    ax.text(
        lo, -0.92, _fmt(lo),
        fontsize=7.0, family="monospace",
        color=_TEXT_MUTED, ha="left", va="bottom",
    )
    ax.text(
        hi, -0.92, _fmt(hi),
        fontsize=7.0, family="monospace",
        color=_TEXT_MUTED, ha="right", va="bottom",
    )

    # No-population hint, when applicable.
    if has_flag and not has_pop:
        ax.text(
            0.5, 0.95,
            f"{label} <- no population",
            transform=ax.transAxes,
            fontsize=7.0, family="monospace",
            color=_TEXT_MUTED, ha="center", va="top", style="italic",
        )

    fig.tight_layout(pad=0.05)
    buf = io.StringIO()
    fig.savefig(
        buf, format="svg", transparent=True,
        bbox_inches="tight", pad_inches=0.04,
    )
    plt.close(fig)
    return buf.getvalue()
