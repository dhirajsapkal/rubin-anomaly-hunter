"""Theme + HTML injection helpers for Streamlit.

Loads dashboard/static/theme.css once per session and injects a small
supplementary block of Streamlit-specific overrides that don't belong in
the design-system-canonical theme.css.
"""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
THEME_CSS_PATH = STATIC_DIR / "theme.css"


_STREAMLIT_OVERRIDES = """
/* ---- Streamlit-specific overrides (not part of design-system contract) --- */

#MainMenu, header[data-testid="stHeader"], footer { visibility: hidden; height: 0; }

[data-testid="stMainBlockContainer"], .block-container {
  padding: 3.5rem 3rem 4rem !important;
  max-width: 1200px !important;
}

[data-testid="stSidebar"] { min-width: 232px !important; width: 232px !important; }
[data-testid="stSidebar"] > div { padding-top: 2.25rem; }

/* Sidebar nav rail — native Streamlit nav, re-skinned */
[data-testid="stSidebar"] [data-testid="stSidebarNav"] ul { padding: 0 0.75rem; list-style: none; }
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a {
  font-family: var(--font-body);
  font-weight: 500;
  font-size: 0.95rem;
  color: var(--text-secondary) !important;
  border-radius: 6px;
  padding: 0.45rem 0.75rem;
  letter-spacing: 0.01em;
  transition: color 160ms var(--ease-calm);
  position: relative;
}
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover {
  color: var(--text-primary) !important;
  background: transparent !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] {
  color: var(--text-primary) !important;
  background: transparent !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"]::before {
  content: "";
  position: absolute;
  left: -4px;
  top: 50%;
  transform: translateY(-50%);
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-phosphor);
}

/* Wordmark block above sidebar nav */
.rh-wordmark {
  padding: 0 var(--sp-4) var(--sp-5);
  border-bottom: 1px solid var(--divider);
  margin-bottom: var(--sp-4);
}
.rh-wordmark .mark {
  font-family: var(--font-display);
  font-weight: 500;
  font-size: 1.125rem;
  color: var(--text-primary);
  letter-spacing: 0.02em;
}
.rh-wordmark .sub {
  font-family: var(--font-body);
  font-style: italic;
  font-size: 0.8rem;
  color: var(--text-tertiary);
  margin-top: 2px;
}

/* Sidebar footer — commissioning/discovery window + config tag */
.rh-rail-footer {
  position: sticky;
  bottom: var(--sp-5);
  padding: var(--sp-4) var(--sp-4) 0;
  margin-top: var(--sp-6);
  border-top: 1px solid var(--divider);
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--text-tertiary);
  line-height: 1.5;
}

/* Streamlit buttons — align with design-system decision palette */
.stButton > button {
  font-family: var(--font-body);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-size: 0.82rem;
  border-radius: var(--radius-md);
  padding: 0.55rem 1.25rem;
  border: 1px solid var(--divider);
  background: var(--surface-card);
  color: var(--text-primary);
  transition: all var(--dur-base) var(--ease-calm);
}
.stButton > button:hover {
  background: var(--surface-card-hover);
  border-color: var(--accent-phosphor-dim);
}

/* Decision-palette variants via button key prefixes -- applied by injecting
   a wrapper class via st.container(border=False). Simpler: style Streamlit
   buttons inside known container classes. */
.decision-accept .stButton > button {
  background: var(--decision-accept); border-color: var(--decision-accept); color: var(--ink-on-paper);
}
.decision-defer  .stButton > button {
  background: transparent; border: 1.5px solid var(--decision-defer); color: var(--decision-defer);
}
.decision-reject .stButton > button {
  background: var(--decision-reject); border-color: var(--decision-reject); color: var(--ink-on-paper);
}
.decision-promote .stButton > button {
  background: var(--decision-promote); border-color: var(--decision-promote);
  color: var(--ink-on-paper);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--decision-promote) 60%, black);
  padding-left: var(--sp-6); padding-right: var(--sp-6);
}

/* Inputs */
.stSelectbox div[data-baseweb="select"] > div,
.stTextInput input, .stTextArea textarea {
  background: var(--surface-card) !important;
  border: 1px solid var(--divider) !important;
  color: var(--text-primary) !important;
  font-family: var(--font-body) !important;
}
.stTextArea textarea { min-height: 80px; }

/* Streamlit markdown headings inside main container */
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2 {
  font-family: var(--font-display);
  font-weight: 500;
  letter-spacing: -0.01em;
}

/* Watch-list row (link form) */
a.wle-row {
  text-decoration: none;
  border-bottom: none;
  color: var(--text-primary);
  display: grid;
  margin-bottom: var(--sp-3);
}
a.wle-row:hover { border-bottom: none; }
a.wle-row span { border-bottom: none; }

/* Pill variants for watch-list statuses (not in theme.css) */
.pill-new      { color: var(--accent-phosphor); background: color-mix(in srgb, var(--accent-phosphor) 15%, transparent); }
.pill-defer    { color: var(--decision-defer);  background: color-mix(in srgb, var(--decision-defer) 18%, transparent); }
.pill-accept   { color: var(--decision-accept); background: color-mix(in srgb, var(--decision-accept) 18%, transparent); }
.pill-reject   { color: var(--decision-reject); background: color-mix(in srgb, var(--decision-reject) 18%, transparent); }

/* Plot frames on paper surface inside a dark card — use paper-card wrapper */
.plot-on-paper { background: var(--surface-paper); border-radius: var(--radius-md); padding: var(--sp-4); }

/* Window banner at top-right of page header */
.window-banner {
  font-family: var(--font-mono);
  font-size: var(--fs-mono-sm);
  color: var(--text-tertiary);
  letter-spacing: 0.04em;
}
.window-banner .sep { padding: 0 var(--sp-2); color: var(--divider); }
.window-banner .tag { color: var(--text-secondary); }

/* Tabs */
[data-baseweb="tab-list"] {
  border-bottom: 1px solid var(--divider) !important;
  gap: var(--sp-5) !important;
}
[data-baseweb="tab"] {
  font-family: var(--font-body) !important;
  font-weight: 500 !important;
  color: var(--text-secondary) !important;
  padding: var(--sp-3) 0 !important;
}
[data-baseweb="tab"][aria-selected="true"] {
  color: var(--text-primary) !important;
  border-bottom: 2px solid var(--accent-phosphor) !important;
}

/* Summary tile sparkline body */
.summary-tile .sparkline-body { margin-top: var(--sp-2); }
.summary-tile .sparkline-body svg { max-width: 100%; height: auto; }

/* QA F7: anchor-styled decision buttons need inline-flex to honor 44px height */
a.btn-decision {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
  border-bottom: none;
}
a.btn-decision:hover { border-bottom: none; }

/* QA H4: decision bar must wrap on narrow viewports */
.decision-bar { flex-wrap: wrap; }

/* Plot frame on paper background — component wraps matplotlib SVGs */
.plot-frame svg { width: 100%; height: auto; display: block; max-width: 100%; }

/* Archive row shows decision pill on a grid layout */
.wle-row.wle-row--archive {
  grid-template-columns: 12px 1fr 180px 140px 160px auto;
}
"""


def inject_theme() -> None:
    """Inject theme.css + overrides on every page render.

    No session-state gate: Streamlit rebuilds the DOM on each page switch, so
    prior <style> blocks are discarded with the old DOM. Gating by session_state
    would leave pages 2..N unstyled after the first load (QA finding F13).
    CSS re-injection is cheap.
    """
    css = ""
    if THEME_CSS_PATH.exists():
        css = THEME_CSS_PATH.read_text(encoding="utf-8")
    st.markdown(
        f"<style>\n{css}\n{_STREAMLIT_OVERRIDES}\n</style>",
        unsafe_allow_html=True,
    )


def wordmark_sidebar() -> None:
    st.markdown(
        """
<div class="rh-wordmark">
  <div class="mark">RUBIN</div>
  <div class="sub">night-log</div>
</div>
""",
        unsafe_allow_html=True,
    )


def sidebar_footer(window_state: str, config_tag: str) -> None:
    label = "commissioning window" if window_state == "commissioning" else "discovery window"
    st.sidebar.markdown(
        f"""
<div class="rh-rail-footer">
  {html.escape(label)}<br/>
  {html.escape(config_tag)}
</div>
""",
        unsafe_allow_html=True,
    )


def kind_pill(category: str) -> str:
    if category == "dark_comet":
        return '<span class="pill pill-kind-dark-comet">DARK COMET</span>'
    if category == "iso":
        return '<span class="pill pill-kind-iso">ISO</span>'
    return f'<span class="pill">{html.escape(category.upper())}</span>'


def status_pill(status: str, decided_date: str | None = None) -> str:
    s = (status or "").lower()
    if s == "promoted":
        # The ONLY place "CANDIDATE" appears in the UI (ADR-0005).
        date_str = f" · {html.escape(decided_date)}" if decided_date else ""
        return f'<span class="pill pill-candidate">CANDIDATE{date_str}</span>'
    if s == "new":
        return '<span class="pill pill-new">NEW</span>'
    if s in {"defer", "deferred"}:
        return '<span class="pill pill-defer">DEFERRED</span>'
    if s in {"accept", "accepted"}:
        return '<span class="pill pill-accept">ACCEPTED</span>'
    if s in {"reject", "rejected"}:
        return '<span class="pill pill-reject">REJECTED</span>'
    return f'<span class="pill">{html.escape(s.upper())}</span>'


def health_pill(state: str, text: str | None = None) -> str:
    s = (state or "ok").lower()
    label = text or s
    return f'<span class="pill pill-health-{s}">{html.escape(label.upper())}</span>'


def window_banner(window_state: str, config_tag: str) -> str:
    label = "commissioning window" if window_state == "commissioning" else "discovery window"
    return (
        '<div class="window-banner">'
        f'<span>{html.escape(label)}</span>'
        f'<span class="sep">·</span>'
        f'<span class="tag">{html.escape(config_tag)}</span>'
        "</div>"
    )


def mono(text: str) -> str:
    return f'<span class="u-mono">{html.escape(text)}</span>'
