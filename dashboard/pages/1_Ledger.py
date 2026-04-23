"""Ledger — append-only history of every decision ever made.

This is the former `Archive` page (renamed per ADR-0014 to reinforce the
append-only, git-tracked framing). Filterable by kind, decision type,
and free text over notes. Clicking a row opens the historical entry in
the Tonight canvas in read-only mode (status is terminal).
"""

from __future__ import annotations

import datetime as dt
import html as _html

import streamlit as st

from lib import db
from lib.components import (
    archive_row_html,
    empty_state_html,
)
from lib.theme import (
    inject_theme,
    provenance_chips_for,
    top_nav,
)


st.set_page_config(
    page_title="Rubin Anomaly Hunter — Ledger",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_theme()


conn = db.get_connection()
summary = db.tonight_summary(conn)
ds_info = db.data_source_info(conn)

# Top nav with provenance chips
st.html(top_nav("Ledger", provenance=provenance_chips_for(ds_info)))

# Page title + subhead
now_iso = dt.datetime.now().strftime("%a %Y-%m-%d · %H:%M")
st.html(
    '<header class="page-head">'
    '<h1 class="page-head__title">Ledger</h1>'
    f'<p class="page-head__meta mono-sm">{_html.escape(now_iso)}  ·  append-only  ·  git-tracked</p>'
    '</header>'
)


# ---- Filters -------------------------------------------------------------

filter_cols = st.columns([1, 1, 2], gap="medium")
with filter_cols[0]:
    kind_filter = st.selectbox(
        "Kind",
        ["all", "dark_comet", "iso"],
        format_func=lambda v: {"all": "All kinds", "dark_comet": "Dark comets", "iso": "ISOs"}[v],
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
            "No decisions logged yet."
            if kind_filter == "all" and decision_filter == "all" and not search
            else "No decisions match these filters.",
            "The first watch-list entry you decide on appears here.",
            "",
            seed_key="ledger-empty",
        ),
        unsafe_allow_html=True,
    )
else:
    counts = {d["decision"]: 0 for d in decisions}
    for d in decisions:
        counts[d["decision"]] = counts.get(d["decision"], 0) + 1
    summary_line = " · ".join(
        f"{counts.get(k, 0)} {label.lower()}"
        for k, label in [
            ("accept",  "accepted"),
            ("defer",   "deferred"),
            ("reject",  "rejected"),
            ("promote", "promoted"),
        ]
        if counts.get(k, 0) > 0
    )
    st.markdown(
        f'<p class="body-sm u-mb-4 u-secondary">'
        f'{len(decisions)} total · {summary_line}'
        f'</p>',
        unsafe_allow_html=True,
    )
    rows_html = "".join(archive_row_html(d) for d in decisions)
    st.html(f'<div class="wle-list">{rows_html}</div>')


# ---- Footer --------------------------------------------------------------

st.markdown(
    '<p class="mono-sm u-mt-8 u-tertiary">'
    "Ledger is append-only. Accepted / rejected / promoted are terminal states; "
    "only deferred entries can be reopened (PRD §F10)."
    '</p>',
    unsafe_allow_html=True,
)
