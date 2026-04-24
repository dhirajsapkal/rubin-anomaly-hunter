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
/* ---- Streamlit chrome overrides — Mission-Control Modern (quiet) --------- */

#MainMenu, header[data-testid="stHeader"], footer { visibility: hidden; height: 0; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stToolbar"] { display: none; }

/* Main container — wider canvas for dense data.
   Reduced top padding because the .rh-topnav strip now owns the top
   56 px of the canvas. */
[data-testid="stMainBlockContainer"], .block-container {
  padding: 1.25rem 3rem 4rem !important;
  max-width: 1360px !important;
}

/* App background — override Streamlit's default */
[data-testid="stAppViewContainer"],
[data-testid="stApp"] {
  background: var(--bg-black) !important;
}

/* Sidebar — retired. Page nav has moved to the .rh-topnav strip.
   Hide the sidebar, its internal page-nav, and the collapse control so
   the canvas is full-width and there's no vestigial rail. */
[data-testid="stSidebar"],
[data-testid="stSidebarContent"],
[data-testid="stSidebarNav"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarNavSeparator"],
[data-testid="collapsedControl"] {
  display: none !important;
  width: 0 !important;
  min-width: 0 !important;
  visibility: hidden !important;
}

/* The sidebar's parent flex container still needs to collapse its gap */
section[data-testid="stMain"] { margin-left: 0 !important; }

/* Wordmark / rail-footer classes preserved for any legacy callers that
   still reference them — rendered inline in the top-nav region now. */
.rh-wordmark {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.8125rem;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--text-primary);
}
.rh-wordmark .mark::before {
  content: "";
  width: 8px;
  height: 8px;
  background: var(--signal);
  border-radius: 2px;
  display: inline-block;
  margin-right: var(--sp-2);
}
.rh-wordmark .sub { display: none; }

.rh-rail-footer {
  font-family: var(--font-mono);
  font-size: var(--fs-micro);
  color: var(--text-tertiary);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.rh-rail-footer .tag {
  color: var(--text-secondary);
  font-size: 10px;
  letter-spacing: 0.06em;
  display: inline;
  margin-left: var(--sp-2);
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

/* Archive-row grid now lives on .wle-row__main--archive in theme.css §28 —
   the anchor itself is a flex-column shell. No override needed here. */

/* Streamlit-emitted <code> pills inside the .card-paper narrative card
   inherit a light default background; override so internal IDs read on dark. */
.card-paper code,
.card-paper pre {
  background: transparent !important;
  border: none !important;
  padding: 0 !important;
  color: var(--text-primary) !important;
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
  {html.escape(label)}
  <span class="tag">{html.escape(config_tag)}</span>
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


# ---- Top navigation strip (replaces the Streamlit sidebar page nav) -------

_NAV_ITEMS: list[tuple[str, str]] = [
    ("Tonight",    "/"),
    ("Past flags", "/Past_flags"),
]


def top_nav(active: str, provenance: dict[str, str] | None = None) -> str:
    """Render the `.rh-topnav` strip with 3 destinations + provenance chips.

    Parameters
    ----------
    active:
        Destination name that should render as the active pill. One of
        ``"Tonight"`` | ``"Past flags"`` (case-insensitive). Health and
        Ledger were retired per ADR-0018.
    provenance:
        Optional mapping of label -> short value rendered as inline chips
        on the right side. Typical keys: ``"INGEST"`` (value ``"LIVE"`` or
        ``"DEMO"``) and ``"ORBITS"`` (value ``"REAL"`` or ``"MOCK"``).
        ``MOCK`` uses the muted-amber variant; ``LIVE`` / ``REAL`` / ``OK``
        use the teal ``--ok`` variant. Anything else is neutral.
    """
    a = (active or "").strip().lower()
    links = []
    for name, href in _NAV_ITEMS:
        is_active = name.lower() == a
        cls = "rh-topnav__link is-active" if is_active else "rh-topnav__link"
        extra = ' aria-current="page"' if is_active else ""
        links.append(
            f'<a class="{cls}" href="{href}" target="_self"{extra}>'
            f'{html.escape(name)}</a>'
        )
    links_html = "".join(links)

    chips_html = ""
    if provenance:
        chips = []
        for label, value in provenance.items():
            vnorm = (value or "").strip().upper()
            variant = "provenance-chip"
            if vnorm in {"LIVE", "REAL", "OK"}:
                variant += " provenance-chip--ok"
            elif vnorm in {"MOCK", "DEMO", "PLACEHOLDER"}:
                variant += " provenance-chip--mock"
            elif vnorm in {"UNDETERMINED", "N/A", "PENDING"}:
                variant += " provenance-chip--warn"
            chips.append(
                f'<span class="{variant}">'
                f'<span class="provenance-chip__label">{html.escape(label)}</span>'
                f'<span class="provenance-chip__value">{html.escape(str(value))}</span>'
                '</span>'
            )
        chips_html = '<div class="rh-topnav__provenance">' + "".join(chips) + "</div>"

    return (
        '<nav class="rh-topnav" role="navigation">'
        '<div class="rh-topnav__brand">'
        '<div class="rh-wordmark"><span class="mark">RUBIN</span></div>'
        '</div>'
        f'<div class="rh-topnav__links">{links_html}</div>'
        '<div class="rh-topnav__spacer"></div>'
        f'{chips_html}'
        '</nav>'
    )


def provenance_chips_for(data_source_info: dict) -> dict[str, str]:
    """Derive the provenance chip dict from dashboard.lib.db.data_source_info.

    INGEST:
      - LIVE  — live.sqlite has triage content from a real Lasair pull
      - DEMO  — falling back to the synthetic demo DB

    ORBITS:
      - REAL          — at least one orbit_fits row was produced by find_orb
      - MOCK          — all existing orbit_fits rows are mock-noise
      - UNDETERMINED  — ingest is live but produced 0 orbit_fits rows
                        (aggregate-only inputs; per-detection arc needed)
    """
    ingest = "LIVE" if data_source_info.get("is_live") else "DEMO"
    if data_source_info.get("orbit_count", 0) == 0 and ingest == "LIVE":
        orbits = "UNDETERMINED"
    elif data_source_info.get("any_mock_fit") or data_source_info.get("any_mock_linker"):
        orbits = "MOCK"
    else:
        orbits = "REAL"
    return {"INGEST": ingest, "ORBITS": orbits}
