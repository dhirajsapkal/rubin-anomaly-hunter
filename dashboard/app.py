"""Rubin Anomaly Hunter — Tonight (home) page.

This is the Streamlit multipage entry point. Additional pages live under
`dashboard/pages/` and are auto-discovered by Streamlit in sidebar order.

Run locally:
    streamlit run dashboard/app.py

The page fulfills Job #1 from docs/ux/brief.md §2: "When I open this, what's
new since last time?" — a first-screen answer in < 3 seconds. Empty state is
the expected state (PRD §15) and is designed as a feature, not a fallback.
"""

from __future__ import annotations

import datetime as dt
import html

import streamlit as st

from lib import db
from lib.components import (
    empty_state_html,
    page_header_html,
    sparkline_tile,
    summary_tile,
)
from lib.theme import (
    inject_theme,
    sidebar_footer,
    window_banner,
    wordmark_sidebar,
)


# ---- Streamlit page config ------------------------------------------------

st.set_page_config(
    page_title="Rubin Anomaly Hunter — Tonight",
    page_icon="·",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()

# ---- Sidebar wordmark (appears above auto-generated page nav) -------------

with st.sidebar:
    wordmark_sidebar()


# ---- Data ----------------------------------------------------------------

conn = db.get_connection()
summary = db.tonight_summary(conn)
health_rows = db.last_n_nights_health(conn, n=14)

sidebar_footer(summary["window_state"], summary["config_tag"])


# ---- Page header ---------------------------------------------------------

now = dt.datetime.now().strftime("%a %Y-%m-%d · %H:%M")
banner_line = (
    ("commissioning window" if summary["window_state"] == "commissioning" else "discovery window")
    + " · "
    + summary["config_tag"]
)
st.markdown(
    page_header_html("Tonight", now_line=now, meta_line=banner_line),
    unsafe_allow_html=True,
)


# ---- Verdict line --------------------------------------------------------

new_total = summary["new_total"]
last_night = summary["last_night"] or "—"

if new_total == 0:
    # One-sentence verdict + honest counts + pipeline truth (PRD §15)
    counts = (
        f"{summary['alerts_ingested_last']:,} alerts ingested · "
        f"{summary['tracklets_linked_last']:,} tracklets linked · "
        f"0 new watch-list entries"
    )
    provenance = f"last ingest night {last_night} · thresholds {summary['config_tag']}"
    st.markdown(
        empty_state_html(
            "Nothing unusual tonight.",
            counts,
            provenance,
            seed_key=last_night,
        ),
        unsafe_allow_html=True,
    )
else:
    # Non-empty: a one-line verdict + three summary tiles
    kind_breakdown = []
    if summary["new_dark_comet"]:
        kind_breakdown.append(f"{summary['new_dark_comet']} dark comet"
                              + ("s" if summary["new_dark_comet"] != 1 else ""))
    if summary["new_iso"]:
        kind_breakdown.append(f"{summary['new_iso']} ISO")
    verdict = f"{new_total} new watch-list entr" + ("ies" if new_total != 1 else "y")
    verdict += " since your last visit"
    st.markdown(
        f'<p class="h3 u-mt-0 u-mb-6" style="color: var(--text-primary); font-weight: 600; font-size: var(--fs-body-lg);">{html.escape(verdict)}</p>',
        unsafe_allow_html=True,
    )

    # Summary tiles (3 across)
    sparkline_values = [r["tracklets_linked"] for r in health_rows]
    sparkline_label = "Tracklets linked — last 14 nights"
    sparkline_current = (
        f"{sparkline_values[-1] if sparkline_values else 0:,} "
        f"on {health_rows[-1]['obs_night']}" if health_rows else ""
    )

    col1, col2, col3 = st.columns([1, 1, 1.4], gap="medium")
    with col1:
        st.markdown(
            summary_tile(
                "New watch-list entries",
                f"{summary['new_total']}",
                breakdown=" · ".join(kind_breakdown) if kind_breakdown else None,
                zero_state=(new_total == 0),
            ),
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            summary_tile(
                "Alerts ingested (last night)",
                f"{summary['alerts_ingested_last']:,}",
                breakdown=f"{summary['tracklets_linked_last']:,} tracklets linked",
            ),
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            sparkline_tile(sparkline_label, sparkline_values, current_text=sparkline_current),
            unsafe_allow_html=True,
        )

    # Promoted-recent note (if any) — small reminder, not a CTA.
    # Deliberately avoids the word "candidate" (ADR-0005 / QA B1) — the archive
    # pill shows "CANDIDATE · <date>" on the row itself.
    if summary["promoted_recent"]:
        st.markdown(
            f'<p class="body-sm u-mt-6" style="color: var(--text-secondary);">'
            f'{summary["promoted_recent"]} promoted from watch list in the last 14 days — '
            f'<a href="/Archive" target="_self">view archive</a></p>',
            unsafe_allow_html=True,
        )


# ---- Tertiary: last-run provenance ---------------------------------------

if new_total > 0:
    st.markdown(
        f'<p class="mono-sm u-mt-6" style="color: var(--text-tertiary);">'
        f"last ingest night {last_night} · thresholds {summary['config_tag']}"
        f"</p>",
        unsafe_allow_html=True,
    )
