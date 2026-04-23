"""Fourteen-night cadence bar chart + single-sentence phrase helper.

Renders a compact bar chart of tracklets-per-night (or alerts-per-night) for
the last 14 UTC nights. Tonight is highlighted in electric amber; historical
nights are charcoal. A p25-p75 baseline band sits behind the bars so the
reader can see at a glance whether tonight is typical or an outlier.

`cadence_summary_phrase` returns a short English fragment describing
tonight's position in the baseline, ready for the narrative lede.

Both functions are pure-data and deterministic. No DB access.
"""

from __future__ import annotations

import io
from statistics import median

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _HAS_MPL = True
except Exception:
    _HAS_MPL = False


_BAR_HIST = "#252C3C"
_BAR_TONIGHT = "#FFB020"
_BASELINE_BAND = "#181E2A"
_TEXT_MUTED = "#5B6275"
_TEXT_SECONDARY = "#9BA3B5"


def _empty_svg(message: str, width: float, height: float) -> str:
    w, h = int(width * 72), int(height * 72)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}">'
        f'<text x="{w//2}" y="{h//2}" text-anchor="middle" '
        f'dominant-baseline="middle" font-family="IBM Plex Mono, monospace" '
        f'font-style="italic" font-size="12" fill="#5B6275">{message}</text>'
        f'</svg>'
    )


def _sorted_nights(nights: list[dict]) -> list[dict]:
    try:
        return sorted(nights, key=lambda n: str(n.get("obs_night", "")))
    except Exception:
        return list(nights)


def cadence_bar_svg(
    nights: list[dict],
    width: float = 5.6,
    height: float = 1.6,
    metric: str = "tracklets",
) -> str:
    """Bar chart over up-to-14 nights. See module docstring.

    Parameters
    ----------
    nights:
        List of ``{"obs_night": "YYYY-MM-DD", "tracklets": int,
        "alerts": int, "is_tonight": bool}``. Order-insensitive (sorted
        ascending by date internally).
    width, height:
        Matplotlib figsize in inches.
    metric:
        Which key to read off each night dict. ``"tracklets"`` or
        ``"alerts"``.
    """
    if not _HAS_MPL:
        return _empty_svg("matplotlib missing", width, height)
    if not nights:
        return _empty_svg("no cadence data", width, height)

    data = _sorted_nights(nights)
    labels = [str(n.get("obs_night", "")) for n in data]
    values = [float(n.get(metric, 0) or 0) for n in data]
    tonight_flags = [bool(n.get("is_tonight")) for n in data]

    historical = [v for v, t in zip(values, tonight_flags) if not t]

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor("none")

    # Strip every spine except the bottom baseline — and keep that one quiet.
    for side, spine in ax.spines.items():
        if side == "bottom":
            spine.set_color("#181E2A")
            spine.set_linewidth(0.8)
        else:
            spine.set_visible(False)

    # Baseline band: p25–p75 of historical only, shown behind the bars.
    xs = np.arange(len(values))
    if len(historical) >= 5:
        p25 = float(np.percentile(historical, 25))
        p75 = float(np.percentile(historical, 75))
        if p75 > p25:
            ax.axhspan(
                p25, p75,
                facecolor=_BASELINE_BAND,
                edgecolor="none",
                alpha=0.9,
                zorder=0,
            )

    # Bars
    colors = [_BAR_TONIGHT if t else _BAR_HIST for t in tonight_flags]
    ax.bar(xs, values, width=0.72, color=colors, zorder=2, linewidth=0)

    # Y-ticks: only min / median / max on the historical range.
    all_vals = [v for v in values if v is not None]
    if all_vals:
        y_min = min(all_vals)
        y_max = max(all_vals)
        y_med = float(median(all_vals))
        ticks = sorted({round(y_min, 2), round(y_med, 2), round(y_max, 2)})
    else:
        ticks = [0]
    ax.set_yticks(ticks)
    ax.set_yticklabels(
        [f"{int(t)}" if float(t).is_integer() else f"{t:g}" for t in ticks]
    )
    for lbl in ax.get_yticklabels():
        lbl.set_fontfamily("monospace")
        lbl.set_color(_TEXT_MUTED)
        lbl.set_fontsize(7.5)

    # X-ticks: first, middle, last.
    n = len(labels)
    if n >= 3:
        tick_idx = [0, n // 2, n - 1]
    elif n == 2:
        tick_idx = [0, 1]
    else:
        tick_idx = [0]
    ax.set_xticks([xs[i] for i in tick_idx])
    short = lambda s: s[5:] if len(s) >= 10 else s  # MM-DD
    ax.set_xticklabels([short(labels[i]) for i in tick_idx])
    for lbl in ax.get_xticklabels():
        lbl.set_fontfamily("monospace")
        lbl.set_color(_TEXT_MUTED)
        lbl.set_fontsize(7.5)

    ax.tick_params(axis="both", which="both", length=0, pad=2)
    ax.set_xlim(-0.6, len(values) - 0.4)

    # Footer text when baseline is still accumulating.
    if len(historical) < 5:
        ax.text(
            0.0, -0.38,
            f"baseline accumulating (N={len(historical)})",
            transform=ax.transAxes,
            fontsize=7.5,
            family="monospace",
            color=_TEXT_MUTED,
            style="italic",
        )

    fig.tight_layout(pad=0.2)
    buf = io.StringIO()
    fig.savefig(
        buf, format="svg", transparent=True,
        bbox_inches="tight", pad_inches=0.1,
    )
    plt.close(fig)
    return buf.getvalue()


def cadence_summary_phrase(nights: list[dict]) -> str:
    """Return a short English phrase describing tonight vs the baseline.

    Examples (all <= 16 words):
      - "3rd-highest tracklet yield in 14 nights"
      - "typical for this window"
      - "quiet — half the median"
      - "baseline still accumulating"
      - "no data yet"
    """
    if not nights:
        return "no data yet"

    data = _sorted_nights(nights)
    tonight = next((n for n in data if n.get("is_tonight")), None)
    historical = [n for n in data if not n.get("is_tonight")]

    if not tonight:
        return "no tonight marker"

    t_val = float(tonight.get("tracklets", 0) or 0)
    hist_vals = [float(n.get("tracklets", 0) or 0) for n in historical]

    if len(hist_vals) < 5:
        return "baseline still accumulating"

    med = float(median(hist_vals))
    # Rank of tonight within (historical + tonight), highest = 1.
    combined_desc = sorted(hist_vals + [t_val], reverse=True)
    rank = combined_desc.index(t_val) + 1
    total = len(combined_desc)

    # Ordinal helper
    def ord_s(n: int) -> str:
        if 10 <= n % 100 <= 20:
            suf = "th"
        else:
            suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suf}"

    # Clear quiet case: well below the median.
    if med > 0 and t_val <= med * 0.55:
        if t_val == 0:
            return "quiet — no tracklets yielded"
        ratio = t_val / med
        # Approximate a natural fraction
        if ratio <= 0.25:
            return "quiet — a quarter of the median"
        if ratio <= 0.6:
            return "quiet — half the median"
        return "quiet — below the baseline band"

    # Strong outlier high.
    if rank <= 3 and t_val > med * 1.25:
        return f"{ord_s(rank)}-highest tracklet yield in {total} nights"

    # Within p25–p75-ish => typical.
    try:
        p25 = float(np.percentile(hist_vals, 25))
        p75 = float(np.percentile(hist_vals, 75))
    except Exception:
        p25, p75 = med * 0.8, med * 1.2
    if p25 <= t_val <= p75:
        return "typical for this window"

    if t_val > p75:
        return "above baseline — upper quartile for this window"
    # else below p25 but not quiet enough to trigger earlier branch
    return "below baseline — lower quartile for this window"
