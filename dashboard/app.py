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
    hero_tonight_html,
    page_header_html,
    sparkline_tile,
    summary_tile,
    telemetry_bar_html,
)
from lib.narrative import generate_hypotheses, generate_why_flagged
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

# Telemetry status bar — mission-control chrome at top of page
new_total = summary["new_total"]
last_night = summary["last_night"] or "—"
telemetry_segments = [
    ("ok", "PIPELINE", "SYNCED"),
    ("", "INGEST", f"{last_night}"),
    ("", "ALERTS", f"{summary['alerts_ingested_last']:,}"),
    ("", "TRACKLETS", f"{summary['tracklets_linked_last']:,}"),
    ("warn" if summary["window_state"] == "commissioning" else "ok",
     summary["window_state"].upper(), summary["config_tag"]),
]
st.markdown(telemetry_bar_html(telemetry_segments), unsafe_allow_html=True)

st.markdown(
    page_header_html("tonight", now_line=now, meta_line=banner_line),
    unsafe_allow_html=True,
)


# ---- Hero numeric + verdict ----------------------------------------------

if new_total == 0:
    # Empty state — the expected state on most nights (PRD §15).
    counts = (
        f"{summary['alerts_ingested_last']:,} alerts ingested · "
        f"{summary['tracklets_linked_last']:,} tracklets linked · "
        f"0 new watch-list entries"
    )
    provenance = f"last ingest night {last_night} · thresholds {summary['config_tag']}"
    st.markdown(
        empty_state_html(
            "nothing unusual tonight.",
            counts,
            provenance,
            seed_key=last_night,
        ),
        unsafe_allow_html=True,
    )
else:
    plural = "entries" if new_total != 1 else "entry"
    verdict_line = f"{new_total} watch-list {plural} arrived since your last visit."
    secondary = (
        f"{summary['alerts_ingested_last']:,} ALERTS · "
        f"{summary['tracklets_linked_last']:,} TRACKLETS"
    )
    st.markdown(
        hero_tonight_html(
            total_new=new_total,
            new_dark_comet=summary["new_dark_comet"],
            new_iso=summary["new_iso"],
            verdict_line=verdict_line,
            secondary=secondary,
        ),
        unsafe_allow_html=True,
    )

    # ---- Tonight's lead story --------------------------------------------
    # Pick the entry most worth leading with: ISO > dark-comet-with-systematic
    # > strongest-non-grav dark comet. This is the hook that turns the home
    # page from "here's a count" into "here's what tonight is about."
    open_entries = db.list_watch_list(conn)
    lead_entry = None
    if open_entries:
        # Prefer ISO if present (rarer)
        isos = [e for e in open_entries if e.get("category") == "iso"]
        if isos:
            lead_entry = isos[0]
        else:
            # Else pick the highest-signal dark comet (largest |A1|)
            dark_comets = [e for e in open_entries if e.get("category") == "dark_comet"]
            if dark_comets:
                lead_entry = max(
                    dark_comets,
                    key=lambda e: abs(float(e.get("A1") or 0)),
                )
    if lead_entry:
        import html as _html
        lead_why = generate_why_flagged(lead_entry)
        lead_hyps = generate_hypotheses(lead_entry)
        leading_name = lead_hyps[0].name if lead_hyps else lead_entry.get("category", "").replace("_", " ").title()
        lead_id = f"wle-0x{lead_entry['entry_id']:08x}"
        others = new_total - 1
        others_line = (
            f" &nbsp;·&nbsp; {others} other watch-list entr{'ies' if others != 1 else 'y'} behind it"
            if others > 0 else ""
        )
        st.markdown(
            f"""
<div class="lead-story">
  <span class="lead-story__label">TONIGHT'S LEAD</span>
  <div>
    <strong style="color: var(--signal);">{_html.escape(leading_name)}</strong>
    — {_html.escape(lead_why.headline.lower())}.
    <a href="/Candidate_Detail?entry_id={lead_entry['entry_id']}" target="_self"
       style="color: var(--text-secondary); border-bottom: 1px solid var(--border-default);">open {_html.escape(lead_id)} →</a>{others_line}
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

    # Secondary tiles — 14-night telemetry
    sparkline_values = [r["tracklets_linked"] for r in health_rows]
    sparkline_current = (
        f"{sparkline_values[-1] if sparkline_values else 0:,}  last night" if sparkline_values else ""
    )

    col1, col2, col3 = st.columns([1, 1, 1.4], gap="medium")
    with col1:
        st.markdown(
            summary_tile(
                "Ingest last night",
                f"{summary['alerts_ingested_last']:,}",
                breakdown="alerts processed",
            ),
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            summary_tile(
                "Tracklets last night",
                f"{summary['tracklets_linked_last']:,}",
                breakdown="heliolinc3d (mock)",
            ),
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            sparkline_tile("Tracklets · 14-night", sparkline_values, current_text=sparkline_current),
            unsafe_allow_html=True,
        )

    # Promoted-recent note (if any) — small reminder, not a CTA.
    # Deliberately avoids the word "candidate" (ADR-0005) — the archive pill
    # carries the CANDIDATE designation on the row itself.
    if summary["promoted_recent"]:
        st.markdown(
            f'<p class="body-sm u-mt-6" style="color: var(--text-secondary);">'
            f'{summary["promoted_recent"]} promoted from watch list in the last 14 days · '
            f'<a href="/Archive" target="_self">open archive</a></p>',
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
