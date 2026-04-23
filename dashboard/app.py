"""Tonight — the single-surface master-detail canvas.

The Rubin Anomaly Hunter dashboard collapses to three destinations:
`Tonight` · `Ledger` · `Health`. This file renders Tonight, which holds:

1. A one-sentence **lede** describing what kind of night this is.
2. An all-sky **Mollweide** map of every detection ingested, with flagged
   entries circled in amber.
3. A 14-night **cadence bar** that frames tonight against the baseline.
4. A **master-detail** band: narrow left gutter listing tonight's open
   watch-list entries + a tracklet group; right canvas opens the active
   entry's narrative/evidence/decision stack. URL-addressable via ``?e=N``.

The old `Watch List` and `Candidate Detail` pages are retired — their
functionality is folded into this surface (ADR-0014). The narrative-first
reading order from ADR-0012 is preserved inside the canvas bands:
narrative → why → hypotheses → evidence → metrics → images → decision.
"""

from __future__ import annotations

import datetime as dt
import html as _html
import json

import streamlit as st

from lib import db
from lib.cadence import cadence_bar_svg, cadence_summary_phrase
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
    generate_night_lede,
    generate_why_flagged,
)
from lib.skymap import all_sky_svg
from lib.strip_plot import strip_plot_svg
from lib.theme import (
    inject_theme,
    kind_pill,
    provenance_chips_for,
    status_pill,
    top_nav,
)


def _clean_svg(svg: str) -> str:
    """Strip matplotlib's XML/DOCTYPE preamble so downstream embedders
    can treat the string as ``<svg>…</svg>`` markup.

    Used for SVGs rendered via ``st.markdown(..., unsafe_allow_html=True)``
    which passes inline SVG through cleanly.
    """
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
    """Render a raw SVG string as a data-URI ``<img>`` so it survives
    ``st.html``'s sanitizer, which strips bare ``<svg>`` blocks.

    Use for any SVG embedded inside a ``st.html(...)`` payload. For SVGs
    going straight into ``st.markdown(unsafe_allow_html=True)`` the inline
    ``_clean_svg()`` form is fine — ``st.markdown`` doesn't strip SVG.
    """
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


# ---- Lede sentence -------------------------------------------------------

cadence_phrase = cadence_summary_phrase(nights)
lede = generate_night_lede(summary, cadence_phrase)
now_iso = dt.datetime.now().strftime("%a %Y-%m-%d · %H:%M")
st.html(
    f'<p class="rh-lede">{_html.escape(lede)}</p>'
    f'<p class="rh-lede__sub">{_html.escape(now_iso)}  ·  '
    f'{_html.escape(summary["config_tag"])}</p>'
)


# ---- Sky map + cadence bar ----------------------------------------------

sky_svg = _clean_svg(all_sky_svg(detections_sky, width=6.6, height=3.0))
cad_svg = _clean_svg(cadence_bar_svg(nights, width=6.6, height=1.35, metric="tracklets"))

st.markdown(
    '<div class="tonight-hero">'
    f'  <figure class="sky-map">{sky_svg}'
    f'    <figcaption class="sky-map__caption">'
    f'Mollweide all-sky · {len(detections_sky)} detections tonight · amber rings = flagged'
    f'    </figcaption>'
    '  </figure>'
    f'  <figure class="cadence-bar">{cad_svg}'
    f'    <figcaption class="cadence-bar__caption">'
    f'14-night tracklet yield · tonight amber · grey band = p25–p75'
    f'    </figcaption>'
    '  </figure>'
    '</div>',
    unsafe_allow_html=True,
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
    kind = (e.get("category") or "").replace("_", "-")
    kind_label = "DARK COMET" if e.get("category") == "dark_comet" else "ISO"
    internal = f"wle-0x{e['entry_id']:08x}"
    date = (e.get("created_utc") or "")[:10]
    status = (e.get("status") or "new").lower()
    status_code = "NEW" if status == "new" else "DEFER" if status in {"defer", "deferred"} else status.upper()
    cls = "gutter-item is-active" if active else "gutter-item"
    return (
        f'<a class="{cls}" href="/?e={e["entry_id"]}" target="_self">'
        f'  <span class="kind-dot kind-dot--{kind}"></span>'
        f'  <span class="gutter-item__id">{_html.escape(internal)}</span>'
        f'  <span class="gutter-item__meta">{_html.escape(kind_label)}</span>'
        f'  <span class="gutter-item__meta">{_html.escape(date)}</span>'
        f'  <span class="gutter-item__meta">{_html.escape(status_code)}</span>'
        f'</a>'
    )


def _render_gutter(entries: list[dict], active_id: int | None) -> str:
    if not entries:
        return (
            '<div class="tonight-gutter__label">OPEN QUEUE</div>'
            '<div class="tonight-gutter__empty">'
            '<p>All clear — no watch-list entries open.</p>'
            '<p class="mono-sm">Most nights, this is what you expect to see.</p>'
            '</div>'
        )
    items = "".join(_gutter_item(e, e["entry_id"] == active_id) for e in entries)
    count = len(entries)
    summary_line = f"{count} open · {sum(1 for e in entries if e.get('status') == 'new')} new"
    # Secondary group — how many tracklets tonight beyond the flagged ones.
    tonight_row = nights[-1] if nights else {}
    n_tracklets = int(tonight_row.get("tracklets") or 0)
    n_flagged = len(entries)
    other = max(0, n_tracklets - n_flagged)
    group_html = (
        '<details class="tonight-gutter__group">'
        f'<summary>+ {other} tracklets linked, not flagged</summary>'
        f'<div class="body-sm u-secondary" style="padding:var(--sp-3);">'
        'These did not trip the scoring gate. Open Ledger to browse past decisions; '
        'per-detection scrub is coming once the Kafka path lands.'
        '</div>'
        '</details>' if other > 0 else ""
    )
    return (
        f'<div class="tonight-gutter__label">OPEN QUEUE · {_html.escape(summary_line)}</div>'
        f'<div class="tonight-gutter__list">{items}</div>'
        f'{group_html}'
    )


# ---- Canvas — active entry's detail stack -------------------------------

def _esc(x) -> str:
    return _html.escape("" if x is None else str(x))


def _provenance_strip(entry: dict, ds: dict) -> str:
    """Small row of provenance chips ABOVE the narrative in the canvas.

    Shows: ingest live/demo, orbit-fit software, whether the fit is mock.
    Replaces the full-width banner the prior design had (ADR-0014 fix).
    """
    sw = (entry.get("software_version") or "").lower()
    fit_is_mock = "mock" in sw
    ingest_live = bool(ds.get("is_live"))
    chips = []
    chips.append(
        '<span class="provenance-chip provenance-chip--ok">'
        '<span class="provenance-chip__label">INGEST</span>'
        f'<span class="provenance-chip__value">{"LIVE" if ingest_live else "DEMO"}</span>'
        '</span>'
    )
    chips.append(
        '<span class="provenance-chip '
        f'{"provenance-chip--mock" if fit_is_mock else "provenance-chip--ok"}">'
        '<span class="provenance-chip__label">ORBIT FIT</span>'
        f'<span class="provenance-chip__value">{"MOCK" if fit_is_mock else "REAL"}</span>'
        '</span>'
    )
    return '<div class="canvas-provenance">' + "".join(chips) + "</div>"


def _canvas_header(entry: dict) -> str:
    category = entry.get("category") or ""
    internal = f"wle-0x{entry['entry_id']:08x}"
    kind_badge = (
        '<span class="kind-badge kind-badge--dark-comet">DARK COMET</span>'
        if category == "dark_comet"
        else '<span class="kind-badge kind-badge--iso">ISO</span>'
    )
    first_seen = (entry.get("created_utc") or "")[:19].replace("T", " ")
    n_obs = entry.get("n_obs") or 0
    n_nights = entry.get("num_nights") or 0
    arc = entry.get("total_arc_hours") or 0.0
    return (
        '<header class="canvas-header">'
        f'<div class="canvas-header__kind">{kind_badge}'
        f'<code class="mono canvas-header__id">{_esc(internal)}</code></div>'
        f'<div class="canvas-header__meta mono-sm">'
        f'{n_obs} det · {n_nights} nights · arc {arc:.1f} h · first seen {_esc(first_seen)}'
        f'</div>'
        f'{status_pill(entry.get("status") or "new")}'
        '</header>'
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
    eyebrow_html = f'<span class="canvas-band__eyebrow">{_esc(eyebrow)}</span>' if eyebrow else ""
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
    """Population strip-plots: e, |A1|, fit_rms — tonight's flagged entry vs. population."""
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
            f'{img}'
            '</div>'
        )

    return (
        _row("e",       pop.get("e", []),        float(e_val) if e_val is not None else None)
        + _row("|A1|",  pop.get("A1_abs", []),   a1_val)
        + _row("rms″", pop.get("fit_rms", []),   float(rms_val) if rms_val is not None else None)
    )


def _decision_bar(entry_id: int, disabled: bool) -> str:
    disabled_cls = " is-disabled" if disabled else ""
    qs = f"e={entry_id}"
    return (
        '<div class="decision-bar">'
        f'<span class="decision-bar__label">ACTION</span>'
        f'<a class="btn-decision btn-accept{disabled_cls}" href="?{qs}&action=accept">ACCEPT</a>'
        f'<a class="btn-decision btn-defer{disabled_cls}" href="?{qs}&action=defer">DEFER</a>'
        f'<a class="btn-decision btn-reject{disabled_cls}" href="?{qs}&pending=reject">REJECT</a>'
        f'<a class="btn-decision btn-promote{disabled_cls}" href="?{qs}&pending=promote">PROMOTE TO CANDIDATE</a>'
        '</div>'
    )


def _render_canvas(entry: dict, ds: dict) -> str:
    why = generate_why_flagged(entry)
    hyps = generate_hypotheses(entry)

    # Detections for the light curve + orbit — optional, may be empty.
    det_ids = entry.get("detection_ids") or []
    det_rows = db.get_detections(conn, det_ids)

    body_sections: list[str] = []

    # 1. Why-flagged narrative (open by default).
    body_sections.append(
        _band(
            "What's weird about this",
            why_flagged_panel_html(why),
            eyebrow="NARRATIVE",
            open_=True,
            modifier="narrative",
        )
    )

    # 2. Hypotheses (open).
    body_sections.append(
        _band(
            "What it could be",
            hypotheses_panel_html(hyps),
            eyebrow="REASONING",
            open_=True,
        )
    )

    # 3. Population rails — new: where does this entry sit vs. tonight's others.
    body_sections.append(
        _band(
            "Compared to tonight's population",
            _population_rails(entry),
            eyebrow="CONTEXT",
            open_=True,
        )
    )

    # 4. Null-hypothesis tests (closed — pass/fail chips visible in summary).
    body_sections.append(
        _band(
            "Null-hypothesis tests",
            null_hypothesis_panel(entry.get("null_tests", {})),
            eyebrow="EVIDENCE",
            open_=False,
        )
    )

    # 5. Orbit fit table (closed).
    body_sections.append(
        _band(
            "Orbit fit",
            orbit_fit_block(entry),
            eyebrow="METRICS",
            open_=False,
        )
    )

    # 6. Cutouts (closed).
    body_sections.append(
        _band(
            "Cutouts · science / template / difference",
            cutouts_strip_html(entry["entry_id"], n_epochs=min((entry.get("n_obs") or 4), 4)),
            eyebrow="IMAGES",
            open_=False,
        )
    )

    # 7. Orbit + light curve plots (closed).
    plot_body = (
        '<div class="canvas-plot-pair">'
        f'<div class="card-paper" style="padding: var(--sp-4);">'
        f'{light_curve_frame_html(entry, det_rows)}</div>'
        f'<div class="card-paper" style="padding: var(--sp-4);">'
        f'{orbit_frame_html(entry)}</div>'
        '</div>'
    )
    body_sections.append(
        _band(
            "Light curve + orbit",
            plot_body,
            eyebrow="MEDIA",
            open_=False,
        )
    )

    status = (entry.get("status") or "new").lower()
    is_readonly = status in {"accept", "accepted", "reject", "rejected", "promoted"}

    return (
        _canvas_header(entry)
        + _provenance_strip(entry, ds)
        + "".join(body_sections)
        + _decision_bar(entry["entry_id"], disabled=is_readonly)
    )


def _render_empty_canvas(summary: dict) -> str:
    alerts = summary.get("alerts_ingested_last", 0)
    tracklets = summary.get("tracklets_linked_last", 0)
    return (
        '<div class="canvas-empty">'
        '<p class="canvas-empty__verdict">Nothing flagged tonight.</p>'
        f'<p class="canvas-empty__counts mono-sm">'
        f'{alerts:,} alerts ingested · {tracklets:,} tracklets linked · 0 watch-list entries.'
        f'</p>'
        '<p class="canvas-empty__aside">'
        "Most nights, the survey says nothing unusual. That's the expected state, not a failure."
        '</p>'
        '</div>'
    )


# ---- Handle decision actions (same URL-driven protocol as before) -------

entry_for_canvas = None
if active_id is not None:
    entry_for_canvas = db.get_watch_list_entry(conn, active_id)

action = params.get("action")
pending = params.get("pending")

if entry_for_canvas and action in {"accept", "defer"}:
    # Only act on non-terminal statuses (double-fire guard).
    status = (entry_for_canvas.get("status") or "new").lower()
    if status not in {"accept", "reject", "promoted"}:
        db.append_decision(conn, active_id, action, "")
        st.query_params.clear()
        st.query_params["e"] = str(active_id)
        st.rerun()

# ---- Emit the grid -------------------------------------------------------

gutter_html = _render_gutter(open_entries, active_id)
canvas_html = (
    _render_canvas(entry_for_canvas, ds_info) if entry_for_canvas
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
    ("known_sso_match", "Known-SSO cross-match confirmed"),
    ("cometary_outgassing_consistent", "Non-grav consistent with normal cometary outgassing"),
    ("image_artifact", "Image artifact / bad subtraction residual"),
    ("streak_residual", "Streak endpoint / satellite trail residual"),
    ("short_arc_ambiguity", "Short-arc ambiguity — orbit not determinable"),
    ("instrument_systematic", "Instrument systematic correlation"),
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
        "Promotion requires independent follow-up astrometry per ADR-0005 Stage B."
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
