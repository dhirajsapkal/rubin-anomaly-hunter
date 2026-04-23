"""Pipeline Health — ingest lag, linking, orbit fits, health pills.

Secondary page per docs/ux/brief.md §3.5 — should be boring on a healthy
night. No red alarms. Reuses the decision palette for health pills so the
user only has to learn four colors across the whole product.
"""

from __future__ import annotations

import datetime as dt

import streamlit as st

from lib import db
from lib.components import (
    health_sparkline_html,
    page_header_html,
)
from lib.theme import inject_theme, sidebar_footer, wordmark_sidebar


st.set_page_config(
    page_title="Rubin Anomaly Hunter — Pipeline Health",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_theme()

with st.sidebar:
    wordmark_sidebar()

conn = db.get_connection()
summary = db.tonight_summary(conn)
sidebar_footer(summary["window_state"], summary["config_tag"])

now = dt.datetime.now().strftime("%a %Y-%m-%d · %H:%M")
st.markdown(
    page_header_html("Pipeline Health", now_line=now, meta_line=summary["config_tag"]),
    unsafe_allow_html=True,
)


# ---- Data ----------------------------------------------------------------

rows = db.last_n_nights_health(conn, n=14)

if not rows:
    st.markdown(
        '<div class="empty-state">'
        '<div class="verdict">No run history.</div>'
        '<div class="counts">Start the pipeline to populate this page.</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()

latest = rows[-1]
alerts_ingested = [r["alerts_ingested"] for r in rows]
tracklets_linked = [r["tracklets_linked"] for r in rows]
orbit_ok = [r["orbit_fits_ok"] for r in rows]
orbit_fail = [r["orbit_fits_failed"] for r in rows]
dropped = [r["dropped_alerts"] for r in rows]
lag_values = [r["ingest_lag_s_p95"] for r in rows]


def _dropped_rate(r: dict) -> float:
    total = (r["alerts_ingested"] or 0) + (r["dropped_alerts"] or 0)
    return (r["dropped_alerts"] / total * 100.0) if total else 0.0


drop_rates = [_dropped_rate(r) for r in rows]


# ---- Current state tiles --------------------------------------------------

def _health_for_lag(v: float) -> str:
    if v < 60:
        return "ok"
    if v < 180:
        return "warn"
    return "error"


def _health_for_drop(v: float) -> str:
    if v < 0.1:
        return "ok"
    if v < 1.0:
        return "warn"
    return "error"


state_lag = _health_for_lag(latest["ingest_lag_s_p95"])
state_drop = _health_for_drop(_dropped_rate(latest))

col1, col2 = st.columns(2, gap="large")
with col1:
    st.markdown(
        health_sparkline_html(
            metric="Ingest lag p95 (24h)",
            values=lag_values,
            current_text=f"current {latest['ingest_lag_s_p95']:.1f}s",
            health_state=state_lag,
            threshold=60.0,
        ),
        unsafe_allow_html=True,
    )
with col2:
    st.markdown(
        health_sparkline_html(
            metric="Dropped alert rate",
            values=drop_rates,
            current_text=f"{drop_rates[-1]:.2f}%",
            health_state=state_drop,
            threshold=0.1,
        ),
        unsafe_allow_html=True,
    )

col3, col4 = st.columns(2, gap="large")
with col3:
    st.markdown(
        health_sparkline_html(
            metric="Alerts ingested / night",
            values=alerts_ingested,
            current_text=f"{latest['alerts_ingested']:,}",
            health_state="ok",
        ),
        unsafe_allow_html=True,
    )
with col4:
    st.markdown(
        health_sparkline_html(
            metric="Tracklets linked / night",
            values=tracklets_linked,
            current_text=f"{latest['tracklets_linked']:,}",
            health_state="ok",
        ),
        unsafe_allow_html=True,
    )

col5, col6 = st.columns(2, gap="large")
with col5:
    fit_ok_rate = latest["orbit_fits_ok"] / max((latest["orbit_fits_ok"] + latest["orbit_fits_failed"]), 1) * 100.0
    st.markdown(
        health_sparkline_html(
            metric="Orbit fits OK (14-night)",
            values=orbit_ok,
            current_text=f"{fit_ok_rate:.1f}%",
            health_state="ok" if fit_ok_rate > 70 else "warn",
        ),
        unsafe_allow_html=True,
    )
with col6:
    st.markdown(
        health_sparkline_html(
            metric="Orbit fits failed",
            values=orbit_fail,
            current_text=f"{latest['orbit_fits_failed']:,}",
            health_state="ok",
        ),
        unsafe_allow_html=True,
    )


# ---- Stage status dots ---------------------------------------------------

st.markdown(
    '<div class="data-label u-mt-8">Last successful stage</div>',
    unsafe_allow_html=True,
)

stages = [
    ("ingest", "ok"),
    ("pre-filter", "ok"),
    ("detection DB commit", "ok"),
    ("heliolinc3d link (mock)", "warn"),
    ("find_orb fit (mock)", "warn"),
    ("MPC xmatch", "ok"),
    ("threshold eval", "ok"),
]

from lib.theme import health_pill

rows_html = []
for label, state in stages:
    rows_html.append(
        '<div style="display:flex; justify-content:space-between; align-items:center;'
        ' padding:var(--sp-3) 0; border-bottom: 1px solid var(--divider);">'
        f'<span class="mono" style="color:var(--text-primary);">{label}</span>'
        f"{health_pill(state)}"
        "</div>"
    )

st.markdown(
    '<div class="card-dark u-mt-4">' + "".join(rows_html) + "</div>",
    unsafe_allow_html=True,
)


# ---- Window + config banner ----------------------------------------------

st.markdown(
    f'<p class="mono-sm u-mt-8" style="color: var(--text-tertiary);">'
    f'pipeline window: <strong>{summary["window_state"]}</strong> · '
    f'thresholds: <strong>{summary["config_tag"]}</strong><br/>'
    f"linking + orbit fits currently running in <strong>mock mode</strong> "
    f"because the find_orb and heliolinc3d binaries are not installed. Install them "
    f"to enable science-grade output (see PRD §12)."
    "</p>",
    unsafe_allow_html=True,
)
