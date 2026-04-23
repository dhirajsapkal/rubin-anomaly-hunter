"""Health — pipeline ingest / linking / orbit-fit telemetry.

Secondary destination (ADR-0014). On a healthy rig this page is boring by
design — no red alarms, just six sparklines and a stage-status column.
Renamed from "Pipeline Health" to "Health" to match the 3-pill top nav.
"""

from __future__ import annotations

import datetime as dt
import html as _html

import streamlit as st

from lib import db
from lib.components import health_sparkline_html
from lib.theme import (
    health_pill,
    inject_theme,
    provenance_chips_for,
    top_nav,
)


st.set_page_config(
    page_title="Rubin Anomaly Hunter — Health",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_theme()


conn = db.get_connection()
summary = db.tonight_summary(conn)
ds_info = db.data_source_info(conn)

st.html(top_nav("Health", provenance=provenance_chips_for(ds_info)))

now = dt.datetime.now().strftime("%a %Y-%m-%d · %H:%M")
st.html(
    '<header class="page-head">'
    '<h1 class="page-head__title">Health</h1>'
    f'<p class="page-head__meta mono-sm">{_html.escape(now)}  ·  {_html.escape(summary["config_tag"])}</p>'
    '</header>'
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
alerts_ingested  = [r["alerts_ingested"]  for r in rows]
tracklets_linked = [r["tracklets_linked"] for r in rows]
orbit_ok         = [r["orbit_fits_ok"]    for r in rows]
orbit_fail       = [r["orbit_fits_failed"] for r in rows]
lag_values       = [r["ingest_lag_s_p95"] for r in rows]


def _dropped_rate(r: dict) -> float:
    total = (r["alerts_ingested"] or 0) + (r["dropped_alerts"] or 0)
    return (r["dropped_alerts"] / total * 100.0) if total else 0.0


drop_rates = [_dropped_rate(r) for r in rows]


def _health_for_lag(v: float) -> str:
    if v < 60:   return "ok"
    if v < 180:  return "warn"
    return "error"


def _health_for_drop(v: float) -> str:
    if v < 0.1:  return "ok"
    if v < 1.0:  return "warn"
    return "error"


state_lag  = _health_for_lag(latest["ingest_lag_s_p95"])
state_drop = _health_for_drop(_dropped_rate(latest))


# ---- 6 sparklines in a 2x3 grid -----------------------------------------

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
    fit_ok_rate = latest["orbit_fits_ok"] / max(
        (latest["orbit_fits_ok"] + latest["orbit_fits_failed"]), 1
    ) * 100.0
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


# ---- Stage status list ---------------------------------------------------

st.markdown(
    '<div class="data-label u-mt-8">Last successful stage</div>',
    unsafe_allow_html=True,
)

# Detect mock-mode from the most recent pipeline_health note.
notes = (latest.get("notes") or "").lower()
link_state = "warn" if "linking=mock" in notes else "ok"
fit_state  = "warn" if "fit=mock"     in notes else "ok"

stages = [
    ("ingest",                      "ok"),
    ("pre-filter",                  "ok"),
    ("detection DB commit",         "ok"),
    ("heliolinc3d link",            link_state),
    ("find_orb fit",                fit_state),
    ("MPC xmatch",                  "ok"),
    ("threshold eval",              "ok"),
]

rows_html = []
for label, state in stages:
    rows_html.append(
        '<div class="health-stage-row">'
        f'<span class="mono">{_html.escape(label)}</span>'
        f'{health_pill(state)}'
        '</div>'
    )

st.markdown(
    '<div class="card-dark u-mt-4">' + "".join(rows_html) + "</div>",
    unsafe_allow_html=True,
)


# ---- Window + config footer ---------------------------------------------

if link_state == "warn" or fit_state == "warn":
    st.markdown(
        f'<p class="mono-sm u-mt-8 u-tertiary">'
        f'pipeline window: <strong>{summary["window_state"]}</strong> · '
        f'thresholds: <strong>{summary["config_tag"]}</strong>'
        f'<br/>linking / orbit fits running in <strong>mock mode</strong> '
        f"because the heliolinc3d / find_orb binaries are not installed. Install them "
        f"(WSL2 on Windows) to enable science-grade output (PRD §12)."
        "</p>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f'<p class="mono-sm u-mt-8 u-tertiary">'
        f'pipeline window: <strong>{summary["window_state"]}</strong> · '
        f'thresholds: <strong>{summary["config_tag"]}</strong>'
        '</p>',
        unsafe_allow_html=True,
    )
