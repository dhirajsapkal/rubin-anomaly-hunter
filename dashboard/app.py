"""Tonight — the hobbyist-first master-detail canvas (ADR-0018).

Structure preserved from ADR-0014 (single-surface, URL-addressable via
``?e=N``); copy and affordances reframed for an amateur operator.

Three panels:
  1. "What the telescope saw tonight" — sky map + plain-English
     explainer card, no jargon in the hero copy.
  2. "Weird things we're watching" — master-detail with the gutter of
     open watch-list entries (plain-language kind subtitles) and the
     per-entry canvas.
  3. "What to do with this flag" — a new canvas band appended after
     the evidence bands, giving concrete follow-up guidance per
     reporting.panel_3_html. Sits above the existing decision bar.

Invariants preserved from ADR-0005 / ADR-0012 / ADR-0011 / ADR-0014:
watch-list ≠ discovery; narrative-first reading order inside the canvas;
Mission-Control Modern palette + typography; master-detail structure.
"""

from __future__ import annotations

import datetime as dt
import html as _html

import streamlit as st

from lib import db, plainlang, reporting
from lib.components import (
    cutouts_strip_html,
    hypotheses_panel_html,
    light_curve_frame_html,
    null_hypothesis_panel,
    orbit_fit_block,
    orbit_frame_html,
    why_flagged_panel_html,
)
from lib.narrative import (
    generate_hypotheses,
    generate_why_flagged,
)
from lib.skymap import all_sky_svg
from lib.strip_plot import strip_plot_svg
from lib.theme import (
    inject_theme,
    provenance_chips_for,
    status_pill,
    top_nav,
)


def _clean_svg(svg: str) -> str:
    """Strip matplotlib's XML/DOCTYPE preamble."""
    if not svg:
        return ""
    s = svg
    if s.lstrip().startswith("<?xml"):
        idx = s.find("?>")
        if idx != -1:
            s = s[idx + 2 :].lstrip()
    if s.lstrip().upper().startswith("<!DOCTYPE"):
        idx = s.find(">")
        if idx != -1:
            s = s[idx + 1 :].lstrip()
    return s


def _svg_as_img(svg: str, *, alt: str = "", css_class: str = "") -> str:
    """Wrap an SVG as data-URI <img> so st.html's sanitiser keeps it."""
    import base64
    if not svg:
        return ""
    cleaned = _clean_svg(svg).encode("utf-8")
    b64 = base64.b64encode(cleaned).decode("ascii")
    cls = f' class="{css_class}"' if css_class else ""
    alt_attr = _html.escape(alt)
    return f'<img{cls} alt="{alt_attr}" src="data:image/svg+xml;base64,{b64}" />'


st.set_page_config(
    page_title="Rubin Anomaly Hunter — Tonight",
    page_icon="·",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_theme()


# ---- Data ----------------------------------------------------------------

conn = db.get_connection()
summary = db.tonight_summary(conn)
ds_info = db.data_source_info(conn)
nights = db.nights_for_cadence(conn, n=14)
detections_sky = db.detections_for_skymap(conn, limit=1000)
open_entries = db.list_watch_list(conn, statuses=("new", "defer"))


# ---- Top nav + provenance chips -----------------------------------------

st.html(top_nav("Tonight", provenance=provenance_chips_for(ds_info)))


# ==========================================================================
# Panel 1 — What the telescope saw tonight
# ==========================================================================

st.html('<div class="panel-section-label">01 · Tonight</div>')


# ---- Plain-English lede --------------------------------------------------

def _lede_html(summary: dict) -> str:
    alerts_tonight = int(summary.get("alerts_ingested_last") or 0)
    n_flagged = int(summary.get("new_total") or 0)
    total_detections = int(summary.get("total_detections") or 0)
    total_tracklets = int(summary.get("total_tracklets") or 0)
    nights_run = int(summary.get("total_health_rows") or 0)

    def _humanize_count(n: int) -> str:
        if n >= 1_000_000:
            return f"~{n // 100_000 / 10:.1f}M".replace(".0M", "M")
        if n >= 100_000:
            return f"~{n // 1_000}k"
        if n >= 10_000:
            return f"~{n // 1_000}k"
        if n >= 1_000:
            return f"~{n // 100 / 10:.1f}k".replace(".0k", "k")
        return f"{n:,}"

    def _weird_clause(n: int) -> str:
        if n == 0:
            return "Nothing flagged so far."
        if n == 1:
            return '<span class="hl-amber">One</span> looks weird enough to watch.'
        return (
            f'<span class="hl-amber">{n}</span> look weird enough to watch.'
        )

    # Three states, ranked by what's most useful to surface:
    # 1. Tonight's batch was loud — describe tonight + flagged.
    # 2. Tonight's batch was quiet but the DB has accumulated history —
    #    describe the cumulative state ("seen so far") so the user
    #    doesn't get a false "nothing happening" read.
    # 3. The DB is genuinely empty — first-boot state.

    if alerts_tonight > 0:
        return (
            "Rubin imaged "
            f'<span class="hl-amber">{_humanize_count(alerts_tonight)}</span> '
            "objects tonight. Most are known asteroids. "
            f"{_weird_clause(n_flagged)}"
        )

    if total_detections > 0:
        nights_phrase = (
            f"{nights_run} night{'s' if nights_run != 1 else ''}"
            if nights_run else "the run so far"
        )
        return (
            "Tonight's poll window was quiet — Rubin didn't drop any new "
            "Solar System alerts in the last cron tick. Across "
            f"{nights_phrase}, the pipeline has seen "
            f'<span class="hl-amber">{_humanize_count(total_detections)}</span> '
            "detections and linked "
            f'<span class="hl-amber">{_humanize_count(total_tracklets)}</span> '
            f"tracklets. {_weird_clause(n_flagged)}"
        )

    return (
        "The pipeline hasn't ingested any alerts yet. "
        "The next scheduled cron tick will pull a fresh batch from Fink."
    )


lede_html = _lede_html(summary)
now_iso = dt.datetime.now().strftime("%a %Y-%m-%d · %H:%M")
last_night = summary.get("last_night") or "—"

st.html(
    f'<p class="rh-lede">{lede_html}</p>'
    f'<p class="rh-lede__sub">{_html.escape(now_iso)} UTC · '
    f'last pipeline tick for {_html.escape(str(last_night))}</p>'
)


# ---- Hero row: sky map + explainer card ---------------------------------

sky_svg = _clean_svg(all_sky_svg(detections_sky, width=6.6, height=3.0))


def _explainer_card_html(summary: dict) -> str:
    n_flagged = int(summary.get("new_total") or 0)
    lead_headline = (
        "Most of the moving dots are known rocks."
        if n_flagged > 0 else
        "Most nights nothing new shows up."
    )
    first_line = (
        "Rubin sees the same asteroid belt every night. Cross-matched "
        "against <strong>the Minor Planet Center catalogue</strong>, "
        "roughly <strong>99.8%</strong> of what moved tonight is "
        "already known."
    )
    second_line = (
        "The pipeline is watching the <strong>amber rings</strong> — "
        "things whose motion doesn't match any known rock."
    )
    third_line = (
        "Two flavors matter most: <span class='t-darkcomet'>dark "
        "comets</span> (accelerating without a visible tail) and "
        "<span class='t-iso'>interstellar objects</span> (on orbits "
        "that came from another star)."
    )
    return (
        '<aside class="explainer-card">'
        '<div>'
        '<div class="explainer-card__eyebrow">What\'s worth knowing</div>'
        f'<div class="explainer-card__title">{lead_headline}</div>'
        '</div>'
        '<div class="explainer-card__items">'
        f'<div class="explainer-card__item explainer-card__item--lead">'
        f'<div class="explainer-card__item-rule"></div><p>{first_line}</p></div>'
        f'<div class="explainer-card__item">'
        f'<div class="explainer-card__item-rule"></div><p>{second_line}</p></div>'
        f'<div class="explainer-card__item">'
        f'<div class="explainer-card__item-rule"></div><p>{third_line}</p></div>'
        '</div></aside>'
    )


n_flagged = int(summary.get("new_total") or 0)
n_detections = len(detections_sky)
sky_legend = (
    '<div class="sky-map__legend">'
    '<div class="sky-map__legend-left">Tonight\'s sky</div>'
    '<div class="sky-map__legend-right">'
    '<div class="sky-map__legend-item">'
    '<span class="dot-known"></span>'
    f'<span>{n_detections:,} detections</span></div>'
    '<div class="sky-map__legend-item sky-map__legend-item--flagged">'
    '<span class="dot-flagged"></span>'
    f'<span>{n_flagged} flagged</span></div>'
    '</div></div>'
)
sky_caption = (
    f'<figcaption class="sky-map__caption">'
    f'Mollweide · equatorial · {n_detections:,} detections shown · '
    f'amber rings = flagged</figcaption>'
)
st.markdown(
    '<div class="hero-row">'
    '<figure class="sky-map">'
    f'{sky_legend}'
    f'{sky_svg}'
    f'{sky_caption}'
    '</figure>'
    f'{_explainer_card_html(summary)}'
    '</div>',
    unsafe_allow_html=True,
)


# ==========================================================================
# Panel 2 — Weird things we're watching
# ==========================================================================

st.html('<div class="panel-section-label">02 · Watch list</div>')
st.html(
    '<div style="display:flex; align-items:baseline; '
    'justify-content:space-between; gap:var(--sp-4); margin-bottom:var(--sp-5);">'
    '<h2 class="h2" style="margin:0;">Weird things we\'re watching</h2>'
    f'<span class="mono-sm" style="color:var(--text-secondary);">'
    f'{len(open_entries)} open · '
    f'{sum(1 for e in open_entries if (e.get("status") or "").lower() == "new")} new'
    '</span></div>'
)


# ---- Master-detail: gutter + canvas -------------------------------------

params = st.query_params


def _active_entry_id() -> int | None:
    raw = params.get("e") or params.get("entry_id")
    if raw is None:
        return open_entries[0]["entry_id"] if open_entries else None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


active_id = _active_entry_id()


def _gutter_item(e: dict, active: bool) -> str:
    kind_slug = (e.get("category") or "dark_comet").replace("_", "-")
    kind_label = plainlang.category_label(e)
    internal = f"wle-0x{e['entry_id']:08x}"
    date = (e.get("created_utc") or "")[:10]
    status = (e.get("status") or "new").lower()
    status_code = (
        "NEW" if status == "new" else
        "DEFERRED" if status in {"defer", "deferred"} else
        status.upper()
    )
    status_cls = (
        " gutter-item__status--defer"
        if status in {"defer", "deferred"} else ""
    )
    n_nights = int(e.get("num_nights") or 0)
    night_phrase = f"{n_nights} night{'s' if n_nights != 1 else ''}" if n_nights else ""
    date_line = (
        f'spotted {_html.escape(date)}'
        + (f' · {night_phrase}' if night_phrase else '')
    )
    cls = "gutter-item is-active" if active else "gutter-item"
    return (
        f'<a class="{cls}" href="/?e={e["entry_id"]}" target="_self">'
        '<div class="gutter-item__topline">'
        f'<span class="gutter-item__id">{_html.escape(internal)}</span>'
        f'<span class="gutter-item__status{status_cls}">'
        f'{_html.escape(status_code)}</span>'
        '</div>'
        '<div class="gutter-item__kindline">'
        f'<span class="kind-dot kind-dot--{kind_slug}"></span>'
        f'<span>{_html.escape(kind_label)}</span>'
        '</div>'
        f'<div class="gutter-item__datestrip">{date_line}</div>'
        '</a>'
    )


def _render_gutter(entries: list[dict], active_id: int | None) -> str:
    if not entries:
        return (
            '<div class="tonight-gutter__label">OPEN QUEUE</div>'
            '<div class="tonight-gutter__empty">'
            '<p>All clear — nothing weird to watch tonight.</p>'
            '<p class="mono-sm">Most nights, this is what you expect '
            'to see.</p>'
            '</div>'
        )
    items = "".join(_gutter_item(e, e["entry_id"] == active_id) for e in entries)
    count = len(entries)
    n_new = sum(1 for e in entries if (e.get("status") or "").lower() == "new")
    summary_line = f"{count} open · {n_new} new"
    tonight_row = nights[-1] if nights else {}
    n_tracklets = int(tonight_row.get("tracklets") or 0)
    n_flagged = len(entries)
    other = max(0, n_tracklets - n_flagged)
    group_html = (
        '<details class="tonight-gutter__group">'
        f'<summary>+ {other} tracklets · not weird</summary>'
        '<div class="body-sm u-secondary" style="padding:var(--sp-3);">'
        "These didn't trip the scoring gate. Open Past flags to "
        "browse decisions you've already made."
        '</div>'
        '</details>'
        if other > 0 else ""
    )
    return (
        f'<div class="tonight-gutter__label">OPEN QUEUE · '
        f'{_html.escape(summary_line)}</div>'
        f'<div class="tonight-gutter__list">{items}</div>'
        f'{group_html}'
    )


# ---- Canvas — active entry's detail stack -------------------------------

def _esc(x) -> str:
    return _html.escape("" if x is None else str(x))


def _canvas_hero(entry: dict) -> str:
    """Plain-English category tag, hero sentence, and stat strip.

    Replaces the mono dense header from ADR-0014 with the ADR-0018
    version: category → hero sentence → three labeled stats.
    """
    category = (entry.get("category") or "").lower()
    kind_cls = "canvas-hero__kind--iso" if category == "iso" else "canvas-hero__kind--darkcomet"
    kind_text = "Interstellar" if category == "iso" else "Dark comet"
    internal = f"wle-0x{entry['entry_id']:08x}"

    sigma_e = entry.get("sigma_e")
    conf = plainlang.confidence_phrase(sigma_e)
    first_phrase = plainlang.first_connected_phrase(entry)
    hero_line = plainlang.hero_sentence(entry)

    first_seen = (entry.get("created_utc") or "")[:19].replace("T", " ")
    n_obs = int(entry.get("n_obs") or 0)
    n_nights = int(entry.get("num_nights") or 0)

    mpc_raw = (entry.get("mpc_crossmatch") or "").strip()
    mpc_miss = not mpc_raw or any(
        tok in mpc_raw.lower() for tok in ("no match", "miss", "none", "unknown")
    )
    mpc_value = "no MPC match &lt; 30'" if mpc_miss else _esc(mpc_raw[:28])

    return (
        '<div class="canvas-hero">'
        '<div class="canvas-hero__chipline">'
        f'<span class="canvas-hero__kind {kind_cls}">{_esc(kind_text)}</span>'
        '<span class="canvas-hero__dot"></span>'
        f'<span class="canvas-hero__chipmeta">{_esc(conf)}</span>'
        '<span class="canvas-hero__dot"></span>'
        f'<span class="canvas-hero__chipmeta">{_esc(first_phrase)}</span>'
        '</div>'
        '<div class="canvas-hero__row">'
        f'<h3 class="canvas-hero__title">{_esc(hero_line)}</h3>'
        f'<code class="canvas-hero__id">{_esc(internal)}</code>'
        '</div>'
        '<div class="canvas-stats">'
        '<div class="canvas-stats__item">'
        '<span class="canvas-stats__label">First spotted</span>'
        f'<span class="canvas-stats__value">{_esc(first_seen)} UTC</span>'
        '</div>'
        '<div class="canvas-stats__sep"></div>'
        '<div class="canvas-stats__item">'
        '<span class="canvas-stats__label">Arc</span>'
        f'<span class="canvas-stats__value">{n_nights} nights · {n_obs} detections</span>'
        '</div>'
        '<div class="canvas-stats__sep"></div>'
        '<div class="canvas-stats__item">'
        '<span class="canvas-stats__label">Known object?</span>'
        f'<span class="canvas-stats__value">{mpc_value}</span>'
        '</div>'
        '</div>'
        '</div>'
    )


def _what_we_saw_band(entry: dict) -> str:
    """Plain-English narrative of the anomaly (ADR-0018 Panel 2)."""
    body = plainlang.what_we_saw(entry)
    return (
        '<div class="band-whatwesaw">'
        '<div class="band-whatwesaw__side">'
        '<span class="band-whatwesaw__side-label">What we saw</span>'
        '</div>'
        '<div class="band-whatwesaw__body">'
        f'<p class="lead">{_esc(body)}</p>'
        '</div></div>'
    )


def _band(
    title: str,
    body_html: str,
    *,
    eyebrow: str = "",
    open_: bool = False,
    modifier: str = "",
) -> str:
    oa = " open" if open_ else ""
    mod = f" canvas-band--{modifier}" if modifier else ""
    eyebrow_html = (
        f'<span class="canvas-band__eyebrow">{_esc(eyebrow)}</span>'
        if eyebrow else ""
    )
    return (
        f'<details class="canvas-band{mod}"{oa}>'
        '<summary class="canvas-band__summary">'
        f'{eyebrow_html}'
        f'<span class="canvas-band__title">{_esc(title)}</span>'
        '<span class="canvas-band__chevron">▾</span>'
        '</summary>'
        f'<div class="canvas-band__body">{body_html}</div>'
        '</details>'
    )


def _population_rails(entry: dict) -> str:
    pop = db.tracklet_population_rails(
        conn, exclude_orbit_fit_id=entry.get("orbit_fit_id")
    )
    e_val = entry.get("e")
    try:
        a1_val = abs(float(entry.get("A1") or 0.0))
    except (TypeError, ValueError):
        a1_val = None
    rms_val = entry.get("fit_rms")

    def _row(label: str, values: list[float], flagged: float | None) -> str:
        svg = strip_plot_svg(values, flagged, label, width=4.0, height=0.45)
        img = _svg_as_img(svg, alt=f"{label} population rail")
        return (
            '<div class="strip-plot-rail">'
            f'<span class="strip-plot-rail__label">{_esc(label)}</span>'
            f'{img}</div>'
        )

    return (
        _row("e", pop.get("e", []), float(e_val) if e_val is not None else None)
        + _row("|A1|", pop.get("A1_abs", []), a1_val)
        + _row("rms\"", pop.get("fit_rms", []), float(rms_val) if rms_val is not None else None)
    )


def _decision_bar(entry_id: int, disabled: bool) -> str:
    disabled_cls = " is-disabled" if disabled else ""
    qs = f"e={entry_id}"
    return (
        '<div class="decision-bar">'
        '<span class="decision-bar__label">ACTION</span>'
        f'<a class="btn-decision btn-accept{disabled_cls}" href="?{qs}&action=accept">ACCEPT</a>'
        f'<a class="btn-decision btn-defer{disabled_cls}" href="?{qs}&action=defer">DEFER</a>'
        f'<a class="btn-decision btn-reject{disabled_cls}" href="?{qs}&pending=reject">REJECT</a>'
        f'<a class="btn-decision btn-promote{disabled_cls}" href="?{qs}&pending=promote">PROMOTE TO CANDIDATE</a>'
        '</div>'
    )


def _first_detection(entry: dict) -> dict | None:
    det_ids = entry.get("detection_ids") or []
    if not det_ids:
        return None
    rows = db.get_detections(conn, det_ids)
    return rows[0] if rows else None


def _render_canvas(entry: dict) -> str:
    why = generate_why_flagged(entry)
    hyps = generate_hypotheses(entry)

    det_ids = entry.get("detection_ids") or []
    det_rows = db.get_detections(conn, det_ids)
    first_det = det_rows[0] if det_rows else None

    body_sections: list[str] = []

    # Plain-English narrative band (new — ADR-0018 replacement for the
    # old "What's weird about this" heading).
    body_sections.append(_what_we_saw_band(entry))

    # What this could be — ranked hypotheses (still uses existing helper).
    body_sections.append(
        _band(
            "What this could be",
            hypotheses_panel_html(hyps),
            eyebrow="Ranked",
            open_=True,
        )
    )

    # Population rails — "compared to tonight's others".
    body_sections.append(
        _band(
            "Compared to tonight's population",
            _population_rails(entry),
            eyebrow="Context",
            open_=True,
        )
    )

    # Why flagged (reasoning trail) — collapsed.
    body_sections.append(
        _band(
            "Why the pipeline flagged this",
            why_flagged_panel_html(why),
            eyebrow="Reasoning",
            open_=False,
        )
    )

    # Null-hypothesis tests — collapsed.
    body_sections.append(
        _band(
            "Things it might be instead",
            null_hypothesis_panel(entry.get("null_tests", {})),
            eyebrow="Checks",
            open_=False,
        )
    )

    # Orbit fit numbers — collapsed, for the curious.
    body_sections.append(
        _band(
            "Orbit fit · the numbers",
            orbit_fit_block(entry),
            eyebrow="Metrics",
            open_=False,
        )
    )

    # Cutouts — collapsed.
    body_sections.append(
        _band(
            "Images",
            cutouts_strip_html(entry["entry_id"], n_epochs=min((entry.get("n_obs") or 4), 4)),
            eyebrow="Evidence",
            open_=False,
        )
    )

    # Orbit + light curve — collapsed.
    plot_body = (
        '<div class="canvas-plot-pair">'
        '<div class="card-paper" style="padding: var(--sp-4);">'
        f'{light_curve_frame_html(entry, det_rows)}</div>'
        '<div class="card-paper" style="padding: var(--sp-4);">'
        f'{orbit_frame_html(entry)}</div>'
        '</div>'
    )
    body_sections.append(
        _band(
            "Light curve + orbit",
            plot_body,
            eyebrow="Media",
            open_=False,
        )
    )

    # Panel 3 — What to do with this flag (new, ADR-0018).
    panel3 = reporting.panel_3_html(entry, first_detection=first_det)

    status = (entry.get("status") or "new").lower()
    is_readonly = status in {"accept", "accepted", "reject", "rejected", "promoted"}

    # Keep the status pill discreetly near the decision bar so the
    # reader still sees the terminal state. Not at the top — the ADR-0018
    # hero is the new primary identity.
    return (
        _canvas_hero(entry)
        + "".join(body_sections)
        + panel3
        + f'<div style="margin-top:var(--sp-4); display:flex; justify-content:flex-end;">'
        f'{status_pill(status)}</div>'
        + _decision_bar(entry["entry_id"], disabled=is_readonly)
    )


def _render_empty_canvas(summary: dict) -> str:
    alerts = summary.get("alerts_ingested_last", 0)
    tracklets = summary.get("tracklets_linked_last", 0)
    return (
        '<div class="canvas-empty">'
        '<p class="canvas-empty__verdict">Nothing weird tonight.</p>'
        '<p class="canvas-empty__counts mono-sm">'
        f'{alerts:,} alerts ingested · {tracklets:,} tracklets linked · '
        '0 watch-list entries.</p>'
        '<p class="canvas-empty__aside">'
        "Most nights, the survey says nothing unusual. That's the "
        "expected state, not a failure."
        '</p></div>'
    )


# ---- Handle decision actions --------------------------------------------

entry_for_canvas = None
if active_id is not None:
    entry_for_canvas = db.get_watch_list_entry(conn, active_id)

action = params.get("action")
pending = params.get("pending")

if entry_for_canvas and action in {"accept", "defer"}:
    status = (entry_for_canvas.get("status") or "new").lower()
    if status not in {"accept", "reject", "promoted"}:
        db.append_decision(conn, active_id, action, "")
        st.query_params.clear()
        st.query_params["e"] = str(active_id)
        st.rerun()


# ---- Emit the grid -------------------------------------------------------

gutter_html = _render_gutter(open_entries, active_id)
canvas_html = (
    _render_canvas(entry_for_canvas) if entry_for_canvas
    else _render_empty_canvas(summary)
)

st.html(
    '<div class="tonight-grid">'
    f'<aside class="tonight-gutter">{gutter_html}</aside>'
    f'<section class="tonight-canvas">{canvas_html}</section>'
    '</div>'
)


# ---- Reject / Promote forms (below the grid) ----------------------------

NULL_TEST_REASONS = [
    ("known_sso_match", "Known-object cross-match confirmed"),
    ("cometary_outgassing_consistent", "Looks like a normal comet with a faint tail"),
    ("image_artifact", "Image artifact / bad subtraction residual"),
    ("streak_residual", "Satellite streak or streak-endpoint"),
    ("short_arc_ambiguity", "Short-arc ambiguity — orbit not determinable"),
    ("instrument_systematic", "Correlates with a specific instrument systematic"),
    ("broker_flag_drift", "Broker flags changed materially since ingest"),
    ("other", "Other (see note)"),
]

if entry_for_canvas and pending == "reject":
    st.markdown(
        '<div class="card-paper u-mt-4" style="padding: var(--sp-5);">'
        '<h3 class="h3" style="margin-bottom: var(--sp-3);">Reject — select reason</h3>'
        '<div class="body-sm u-secondary u-mb-4">'
        "A reason is required (PRD §10 null-hypothesis checklist)."
        '</div>',
        unsafe_allow_html=True,
    )
    with st.form("reject_form", clear_on_submit=False):
        keys = [k for k, _ in NULL_TEST_REASONS]
        labels = {k: lab for k, lab in NULL_TEST_REASONS}
        reason = st.selectbox(
            "Reason", keys, format_func=lambda k: labels[k],
        )
        note = st.text_area(
            "Note (optional unless Other)",
            placeholder="One-line rationale for the ledger record…",
        )
        c1, c2 = st.columns([1, 1])
        with c1:
            cancel = st.form_submit_button("Cancel")
        with c2:
            confirm = st.form_submit_button("Confirm reject")
        if cancel:
            st.query_params.clear()
            st.query_params["e"] = str(active_id)
            st.rerun()
        if confirm:
            if reason == "other" and not note.strip():
                st.error("A note is required when Other is selected.")
            else:
                full = labels[reason]
                if note.strip():
                    full += " — " + note.strip()
                db.append_decision(conn, active_id, "reject", full)
                st.query_params.clear()
                st.query_params["e"] = str(active_id)
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

if entry_for_canvas and pending == "promote":
    st.markdown(
        '<div class="card-paper u-mt-4" style="padding: var(--sp-5);">'
        '<h3 class="h3" style="margin-bottom: var(--sp-3);">Promote to candidate — attach follow-up evidence</h3>'
        '<div class="body-sm u-secondary u-mb-4">'
        "Promotion requires independent follow-up astrometry from a second "
        "observatory (ADR-0005 Stage B). Until that lands, this stays on the "
        "watch-list as a flag, not a candidate."
        '</div>',
        unsafe_allow_html=True,
    )
    with st.form("promote_form", clear_on_submit=False):
        evidence = st.text_input(
            "Evidence reference",
            placeholder="e.g. MPEC 2026-XNN, ATEL #XXXXX, /local/path/astrometry.ades",
        )
        note = st.text_area(
            "Confirmation note",
            placeholder="Refit with extended arc held signature within σ. …",
        )
        c1, c2 = st.columns([1, 1])
        with c1:
            cancel = st.form_submit_button("Cancel")
        with c2:
            confirm = st.form_submit_button("Promote to candidate")
        if cancel:
            st.query_params.clear()
            st.query_params["e"] = str(active_id)
            st.rerun()
        if confirm:
            if not evidence.strip():
                st.error("Evidence reference is required to promote.")
            else:
                full = f"evidence: {evidence.strip()}"
                if note.strip():
                    full += " — " + note.strip()
                db.append_decision(conn, active_id, "promote", full)
                st.query_params.clear()
                st.query_params["e"] = str(active_id)
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
