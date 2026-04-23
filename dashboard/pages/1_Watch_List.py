"""Watch List — triage queue for dark-comet and ISO watch-list entries.

Two top-level tabs per docs/ux/brief.md §3.2: Dark comets (default per
ADR-0004) and ISOs. Tabs are deliberate: the populations are scientifically
distinct and the UI must say so. See ADR-0005 for strict language rules —
"candidate" and "discovery" do not appear on this page.
"""

from __future__ import annotations

import datetime as dt
import html

import streamlit as st

from lib import db
from lib.components import (
    empty_state_html,
    page_header_html,
    watch_list_row_html,
)
from lib.theme import (
    inject_theme,
    sidebar_footer,
    wordmark_sidebar,
)


st.set_page_config(
    page_title="Rubin Anomaly Hunter — Watch List",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_theme()

with st.sidebar:
    wordmark_sidebar()

conn = db.get_connection()
summary = db.tonight_summary(conn)
sidebar_footer(summary["window_state"], summary["config_tag"])


# ---- Page header ---------------------------------------------------------

now = dt.datetime.now().strftime("%a %Y-%m-%d · %H:%M")
st.markdown(
    page_header_html("Watch List", now_line=now, meta_line=summary["config_tag"]),
    unsafe_allow_html=True,
)


# ---- Load entries and split by kind --------------------------------------

dark_comets = db.list_watch_list(conn, category="dark_comet")
isos = db.list_watch_list(conn, category="iso")


def _render_list(entries: list[dict], kind: str) -> None:
    if not entries:
        verdict = (
            "All dark-comet entries reviewed."
            if kind == "dark_comet"
            else "No open ISO watch-list entries."
        )
        counts = "watch-list empty — all entries accepted / rejected / promoted."
        st.markdown(
            empty_state_html(verdict, counts, "", seed_key=kind + "-empty"),
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="u-center u-mt-4"><a href="/Archive" target="_self">view archive →</a></div>',
            unsafe_allow_html=True,
        )
        return

    # Header row with counts
    n_open = sum(1 for e in entries if (e.get("status") or "new") == "new")
    n_def = sum(1 for e in entries if (e.get("status") or "") == "defer")
    kind_label = "Dark comets" if kind == "dark_comet" else "ISOs"
    st.markdown(
        f'<div class="body-sm u-mb-4" style="color: var(--text-secondary);">'
        f'{kind_label} · {n_open} new · {n_def} deferred'
        f"</div>",
        unsafe_allow_html=True,
    )

    # Render each row
    for e in entries:
        st.markdown(watch_list_row_html(e), unsafe_allow_html=True)


tab_dc, tab_iso = st.tabs([
    f"Dark comets ({len([e for e in dark_comets if e.get('status') in ('new','defer')])} open)",
    f"ISOs ({len([e for e in isos if e.get('status') in ('new','defer')])} open)",
])

with tab_dc:
    _render_list(dark_comets, "dark_comet")

with tab_iso:
    _render_list(isos, "iso")


# No footer copy on this page. Language rules are encoded structurally
# (the Promote action lives on the detail page, not here — ADR-0005).
