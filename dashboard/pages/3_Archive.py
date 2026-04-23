"""Archive — append-only history of every decision ever made.

Filterable by kind, decision type, and free text over notes. Clicking a row
opens the historical Candidate Detail view for that entry in read-only mode
(the Candidate Detail page auto-detects a terminal status).
"""

from __future__ import annotations

import datetime as dt
import html

import streamlit as st

from lib import db
from lib.components import (
    archive_row_html,
    empty_state_html,
    page_header_html,
)
from lib.theme import inject_theme, sidebar_footer, wordmark_sidebar


st.set_page_config(
    page_title="Rubin Anomaly Hunter — Archive",
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
    page_header_html("Archive", now_line=now, meta_line="append-only · git-tracked"),
    unsafe_allow_html=True,
)


# ---- Filters -------------------------------------------------------------

filter_cols = st.columns([1, 1, 2], gap="medium")
with filter_cols[0]:
    kind_filter = st.selectbox(
        "Kind",
        ["all", "dark_comet", "iso"],
        format_func=lambda v: {"all": "All", "dark_comet": "Dark comets", "iso": "ISOs"}[v],
        label_visibility="collapsed",
    )
with filter_cols[1]:
    decision_filter = st.selectbox(
        "Decision",
        ["all", "accept", "defer", "reject", "promote"],
        format_func=lambda v: {
            "all": "All decisions",
            "accept": "Accepted",
            "defer": "Deferred",
            "reject": "Rejected",
            "promote": "Promoted",
        }[v],
        label_visibility="collapsed",
    )
with filter_cols[2]:
    search = st.text_input(
        "Search notes",
        placeholder="search notes…",
        label_visibility="collapsed",
    )


# ---- Fetch ----------------------------------------------------------------

decisions = db.list_decisions(
    conn,
    kind=None if kind_filter == "all" else kind_filter,
    decision=None if decision_filter == "all" else decision_filter,
)

if search:
    s_lower = search.lower()
    decisions = [d for d in decisions if s_lower in (d.get("note") or "").lower()]


# ---- Render ---------------------------------------------------------------

if not decisions:
    st.markdown(
        empty_state_html(
            "No decisions match these filters." if kind_filter != "all" or decision_filter != "all" or search
            else "No decisions logged yet.",
            "The first watch-list entry you review will appear here.",
            "",
            seed_key="archive-empty",
        ),
        unsafe_allow_html=True,
    )
else:
    # Summary line
    counts = {d["decision"]: 0 for d in decisions}
    for d in decisions:
        counts[d["decision"]] = counts.get(d["decision"], 0) + 1
    summary_line = " · ".join(
        f"{counts.get(k, 0)} {label.lower()}"
        for k, label in [("accept", "accepted"), ("defer", "deferred"),
                         ("reject", "rejected"), ("promote", "promoted")]
        if counts.get(k, 0) > 0
    )
    st.markdown(
        f'<div class="body-sm u-mb-4" style="color:var(--text-secondary);">'
        f'{len(decisions)} total · {summary_line}'
        f"</div>",
        unsafe_allow_html=True,
    )
    for d in decisions:
        st.markdown(archive_row_html(d), unsafe_allow_html=True)


# ---- Footer note ----------------------------------------------------------

st.markdown(
    '<p class="mono-sm u-mt-8" style="color: var(--text-tertiary);">'
    "Decisions are append-only. Accepted / rejected / promoted are terminal states; "
    "only deferred entries can be reopened (PRD §F10)."
    "</p>",
    unsafe_allow_html=True,
)
