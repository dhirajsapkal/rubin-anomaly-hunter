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
/* ---- Streamlit chrome overrides — Mission-Control Modern ----------------- */

#MainMenu, header[data-testid="stHeader"], footer { visibility: hidden; height: 0; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stToolbar"] { display: none; }

/* Main container — wider canvas for dense data */
[data-testid="stMainBlockContainer"], .block-container {
  padding: 2.75rem 3rem 4rem !important;
  max-width: 1360px !important;
}

/* App background — override Streamlit's default */
[data-testid="stAppViewContainer"],
[data-testid="stApp"] {
  background: var(--bg-black) !important;
}

/* Sidebar — operational nav rail */
[data-testid="stSidebar"] {
  min-width: 240px !important;
  width: 240px !important;
  background: var(--bg-deep) !important;
  border-right: 1px solid var(--border-default) !important;
}
[data-testid="stSidebar"] > div { padding-top: 1.5rem; }

/* Native Streamlit page nav — re-skinned for ops console */
[data-testid="stSidebarNav"] ul {
  padding: var(--sp-2) var(--sp-3);
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
[data-testid="stSidebarNav"] a {
  font-family: var(--font-body) !important;
  font-weight: 500 !important;
  font-size: var(--fs-body-sm) !important;
  color: var(--text-secondary) !important;
  padding: var(--sp-2) var(--sp-3) !important;
  border-radius: var(--r-sm) !important;
  letter-spacing: 0 !important;
  transition: color 140ms var(--ease), background 140ms var(--ease) !important;
  position: relative;
  border-left: 2px solid transparent !important;
}
[data-testid="stSidebarNav"] a span { color: inherit !important; }
[data-testid="stSidebarNav"] a:hover {
  color: var(--text-primary) !important;
  background: var(--bg-surface-1) !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"] {
  color: var(--text-primary) !important;
  background: var(--bg-surface-1) !important;
  border-left-color: var(--signal) !important;
}
/* Hide the default page-icons Streamlit injects */
[data-testid="stSidebarNavSeparator"],
[data-testid="stSidebarNav"] a svg { display: none !important; }

/* Wordmark in the sidebar */
.rh-wordmark {
  padding: var(--sp-3) var(--sp-5) var(--sp-5);
  border-bottom: 1px solid var(--border-default);
  margin-bottom: var(--sp-3);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.rh-wordmark .mark {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 1rem;
  color: var(--text-primary);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.rh-wordmark .mark::before {
  content: "";
  width: 8px;
  height: 8px;
  background: var(--signal);
  box-shadow: 0 0 12px rgba(255, 176, 32, 0.7);
  border-radius: 2px;
  display: inline-block;
  animation: signalPulse 2s ease-in-out infinite;
}
.rh-wordmark .sub {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--text-tertiary);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  padding-left: 18px;
}

/* Sidebar footer — commissioning/discovery window banner */
.rh-rail-footer {
  padding: var(--sp-4) var(--sp-5);
  margin-top: var(--sp-5);
  border-top: 1px solid var(--border-default);
  font-family: var(--font-mono);
  font-size: var(--fs-micro);
  color: var(--text-tertiary);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  line-height: 1.7;
}
.rh-rail-footer strong {
  color: var(--signal);
  font-weight: 500;
  display: block;
  letter-spacing: 0.08em;
}

/* Streamlit button base — paired with decision classes below */
.stButton > button {
  font-family: var(--font-body);
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-size: var(--fs-body-sm);
  border-radius: var(--r-sm);
  padding: 0.5rem 1.1rem;
  border: 1px solid var(--border-default);
  background: var(--bg-surface-2);
  color: var(--text-primary);
  transition: all var(--dur-base) var(--ease);
  min-height: 40px;
}
.stButton > button:hover {
  background: var(--bg-surface-3);
  border-color: var(--border-strong);
  color: var(--text-primary);
}
.stButton > button:focus-visible {
  outline: 2px solid var(--signal) !important;
  outline-offset: 2px;
}
.stButton > button:active { transform: scale(0.98); }

.stButton > button[kind="primary"],
button[data-testid="baseButton-primary"] {
  background: var(--signal) !important;
  border-color: var(--signal) !important;
  color: var(--text-inverted) !important;
}

/* Form submit buttons inside reject / promote forms */
[data-testid="stForm"] .stButton > button {
  min-width: 120px;
}

/* Inputs — match dark surfaces */
.stSelectbox div[data-baseweb="select"] > div,
.stTextInput input,
.stTextArea textarea,
[data-baseweb="input"] input {
  background: var(--bg-surface-2) !important;
  border: 1px solid var(--border-default) !important;
  color: var(--text-primary) !important;
  font-family: var(--font-mono) !important;
  font-size: var(--fs-body-sm) !important;
  border-radius: var(--r-sm) !important;
}
.stSelectbox div[data-baseweb="select"] > div:hover,
.stTextInput input:focus,
.stTextArea textarea:focus {
  border-color: var(--signal) !important;
}
.stTextArea textarea { min-height: 88px; }

/* BaseWeb select dropdown styling */
[data-baseweb="popover"] [data-baseweb="menu"] {
  background: var(--bg-surface-2) !important;
  border: 1px solid var(--border-default) !important;
  border-radius: var(--r-sm) !important;
}
[data-baseweb="popover"] li[role="option"] {
  background: transparent !important;
  color: var(--text-primary) !important;
  font-family: var(--font-mono) !important;
  font-size: var(--fs-body-sm) !important;
}
[data-baseweb="popover"] li[role="option"]:hover {
  background: var(--bg-surface-3) !important;
  color: var(--text-primary) !important;
}

/* Labels in forms */
.stSelectbox label, .stTextInput label, .stTextArea label {
  font-family: var(--font-mono) !important;
  font-size: var(--fs-micro) !important;
  text-transform: uppercase !important;
  letter-spacing: 0.14em !important;
  color: var(--text-tertiary) !important;
  font-weight: 500 !important;
}

/* Streamlit columns — no extra background */
[data-testid="column"] { background: transparent; }

/* Tabs — the Watch List has two */
[data-baseweb="tab-list"] {
  background: transparent !important;
  border-bottom: 1px solid var(--border-default) !important;
  gap: 0 !important;
  padding: 0 !important;
}
[data-baseweb="tab"] {
  font-family: var(--font-mono) !important;
  font-weight: 500 !important;
  font-size: var(--fs-body-sm) !important;
  text-transform: uppercase !important;
  letter-spacing: 0.12em !important;
  color: var(--text-tertiary) !important;
  padding: var(--sp-3) var(--sp-5) !important;
  background: transparent !important;
  border-bottom: 2px solid transparent !important;
  transition: color var(--dur-base) var(--ease), border-color var(--dur-base) var(--ease) !important;
}
[data-baseweb="tab"]:hover {
  color: var(--text-secondary) !important;
}
[data-baseweb="tab"][aria-selected="true"] {
  color: var(--text-primary) !important;
  border-bottom-color: var(--signal) !important;
}

/* Streamlit alerts/errors inside forms */
[data-testid="stAlert"],
.stAlert {
  background: var(--bg-surface-2) !important;
  border: 1px solid var(--border-default) !important;
  border-radius: var(--r-sm) !important;
  color: var(--text-primary) !important;
}

/* Markdown headings inside main */
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3 {
  font-family: var(--font-display) !important;
  font-weight: 600 !important;
  letter-spacing: -0.02em !important;
  color: var(--text-primary) !important;
}

/* Streamlit vertical block spacing — tighten */
[data-testid="stVerticalBlock"] { gap: var(--sp-4); }

/* Remove the default column gutter "card" look */
[data-testid="stHorizontalBlock"] { gap: var(--sp-4) !important; }

/* Reduce native Streamlit font bloat on body elements */
.stMarkdown, .stText, .stWrite {
  font-family: var(--font-body);
  font-size: var(--fs-body);
  color: var(--text-primary);
}

/* Archive row adds a 6-col grid variant */
.wle-row.wle-row--archive {
  grid-template-columns: 10px 112px 1fr 120px 140px 1fr;
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
