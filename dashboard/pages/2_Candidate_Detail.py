"""Candidate Detail — one watch-list entry, all load-bearing data, decision bar.

Strict language rules (docs/ux/brief.md §5, ADR-0005):
 - Page title is "Watch-list entry", never "Candidate".
 - "Candidate" appears only inside the explicit *Promote to candidate* action
   and as a post-promote pill on archived entries.
 - "Discovery" appears nowhere in this UI.

Deep-linked via ?entry_id=N from the Watch List page. Actions are URL-driven
so the user's browser back button remains meaningful.
"""

from __future__ import annotations

import datetime as dt
import html

import streamlit as st

from lib import db
from lib.components import (
    archive_row_html,  # noqa: F401  # reserved for decision-history strip
    cutouts_strip_html,
    empty_state_html,
    light_curve_frame_html,
    null_hypothesis_panel,
    orbit_fit_block,
    orbit_frame_html,
    page_header_html,
)
from lib.theme import (
    inject_theme,
    kind_pill,
    sidebar_footer,
    status_pill,
    wordmark_sidebar,
)


st.set_page_config(
    page_title="Rubin Anomaly Hunter — Watch-list entry",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_theme()

with st.sidebar:
    wordmark_sidebar()

conn = db.get_connection()
summary = db.tonight_summary(conn)
sidebar_footer(summary["window_state"], summary["config_tag"])


# ---- Resolve entry_id from query params ----------------------------------

params = st.query_params
entry_id_raw = params.get("entry_id")
try:
    entry_id = int(entry_id_raw) if entry_id_raw else None
except (TypeError, ValueError):
    entry_id = None

if entry_id is None:
    st.markdown(
        page_header_html("Watch-list entry"),
        unsafe_allow_html=True,
    )
    st.markdown(
        empty_state_html(
            "Select a watch-list entry.",
            "Open an entry from the Watch List page to review it here.",
            "",
            seed_key="candidate-detail-empty",
        ),
        unsafe_allow_html=True,
    )
    st.stop()

entry = db.get_watch_list_entry(conn, entry_id)
if entry is None:
    st.markdown(page_header_html("Watch-list entry"), unsafe_allow_html=True)
    st.markdown(
        empty_state_html(
            "That watch-list entry is no longer in the active queue.",
            "It may have been archived. ",
            f"entry_id={entry_id}",
            seed_key=str(entry_id),
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="u-center u-mt-4"><a href="Archive" target="_self">view in archive →</a></div>',
        unsafe_allow_html=True,
    )
    st.stop()


# ---- Handle decision actions from URL ------------------------------------

action = params.get("action")
pending = params.get("pending")

NULL_TEST_REASONS = [
    ("known_sso_match", "Known-SSO cross-match confirmed"),
    ("cometary_outgassing_consistent", "Non-grav consistent with normal cometary outgassing"),
    ("image_artifact", "Image artifact / bad subtraction residual"),
    ("streak_residual", "Streak endpoint / satellite trail residual"),
    ("short_arc_ambiguity", "Short-arc ambiguity — orbit not determinable"),
    ("instrument_systematic", "Instrument systematic correlation"),
    ("broker_flag_drift", "Broker flags changed materially since ingest"),
    ("other", "Other (see note)"),
]


def _process_action(
    action_: str,
    note: str,
) -> None:
    """Append a decision and rerun so the page renders in read-only mode.

    No auto-navigation away: the user sees the archived summary for the entry
    they just decided on, and navigates back to Watch List from the sidebar
    when they are ready. This avoids switch_page's context-sensitive path
    behavior and gives the user a confirming render of their action.
    """
    db.append_decision(conn, entry_id, action_, note)
    st.session_state["_last_decision"] = {
        "entry_id": entry_id,
        "action": action_,
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
    }
    # Keep entry_id, drop action / pending
    st.query_params.clear()
    st.query_params["entry_id"] = str(entry_id)
    st.rerun()


# ---- Read-only mode for archived entries ---------------------------------

# Terminal statuses match the schema's CHECK constraint. Defer is NOT terminal
# (deferred entries can be reopened per docs/ux/brief.md §6).
terminal_statuses = {"accept", "reject", "promoted"}
is_readonly = (entry.get("status") or "").lower() in terminal_statuses


# Process accept/defer actions only if the entry is still active — prevents
# double-fire when the user uses the browser Back button (QA B5).
if not is_readonly:
    if action == "accept":
        _process_action("accept", "")
    elif action == "defer":
        _process_action("defer", "")


# ---- Header --------------------------------------------------------------

category = entry.get("category", "")
internal = f"wle-0x{entry['entry_id']:08x}"
threshold_tag = entry.get("config_tag") or summary["config_tag"]
first_seen = (entry.get("created_utc") or "")[:19].replace("T", " ")
st.markdown(
    page_header_html(
        "Watch-list entry",
        now_line=internal,
        meta_line=f"{threshold_tag}  ·  first seen {first_seen}",
    ),
    unsafe_allow_html=True,
)


# ---- Paper card body -----------------------------------------------------

n_obs = entry.get("n_obs") or 0
n_nights = entry.get("num_nights") or 0
arc_hours = entry.get("total_arc_hours") or 0.0

kind_badge = (
    '<span class="kind-badge kind-badge--dark-comet">DARK COMET</span>'
    if category == "dark_comet"
    else '<span class="kind-badge kind-badge--iso">ISO</span>'
)
status_el = status_pill(entry.get("status") or "new")
mpc_text = entry.get("mpc_crossmatch") or "no match"

header_row = (
    '<div style="display:flex; align-items:baseline; justify-content:space-between; '
    'flex-wrap:wrap; gap:var(--sp-3); margin-bottom:var(--sp-4);">'
    f'<div style="display:flex; align-items:baseline; gap:var(--sp-3);">'
    f'{kind_badge}'
    f'<code class="mono" style="font-size: var(--fs-body);">{internal}</code>'
    f"</div>"
    f'<div style="display:flex; align-items:center; gap:var(--sp-3);">'
    f"{status_el}"
    f'</div>'
    "</div>"
)

# Tracklet meta line
tracklet_meta = (
    f'<div class="data-block data-block--paper" style="margin-bottom:var(--sp-5);">'
    f"{n_obs} detections across {n_nights} night{'s' if n_nights != 1 else ''} · "
    f"arc {arc_hours:.1f} h"
    f"</div>"
)

notes_html = ""
if entry.get("notes"):
    notes_html = (
        f'<div class="data-label data-label--paper u-mt-6">Pipeline notes</div>'
        f'<div class="body" style="color:var(--ink-on-paper); margin-top:var(--sp-2);">'
        f"{html.escape(entry['notes'])}</div>"
    )

mpc_html = (
    f'<div class="data-label data-label--paper u-mt-6">MPC cross-match</div>'
    f'<div class="body" style="color:var(--ink-on-paper); margin-top:var(--sp-2);">'
    f"{html.escape(mpc_text)}</div>"
)

# Build the paper card body
card_body = (
    '<div class="card-paper">'
    f"{header_row}"
    f"{tracklet_meta}"
    f"{null_hypothesis_panel(entry.get('null_tests', {}))}"
    '<hr class="divider-paper">'
    f"{orbit_fit_block(entry)}"
    '<hr class="divider-paper">'
    f"{cutouts_strip_html(entry_id, n_epochs=min(n_obs, 4))}"
    "</div>"
)

st.markdown(card_body, unsafe_allow_html=True)


# ---- Orbit + light curve side-by-side ------------------------------------

# Synthesize a tracklet's worth of detections for the light curve preview.
# Real detections are in entry['detection_ids']; retrieve them when populated.
detection_rows = db.get_detections(conn, entry.get("detection_ids", []))

col_lc, col_orb = st.columns([1.4, 1], gap="large")
with col_lc:
    st.markdown(
        '<div class="card-paper" style="padding: var(--sp-4);">'
        + light_curve_frame_html(entry, detection_rows)
        + "</div>",
        unsafe_allow_html=True,
    )
with col_orb:
    st.markdown(
        '<div class="card-paper" style="padding: var(--sp-4);">'
        + orbit_frame_html(entry)
        + "</div>",
        unsafe_allow_html=True,
    )


# ---- Cross-broker + MPC + notes ------------------------------------------

st.markdown(
    '<div class="card-paper u-mt-6" style="padding: var(--sp-5);">'
    '<div class="data-label data-label--paper">Cross-broker context (snapshot at ingest)</div>'
    '<div class="mono u-mt-4" style="color:var(--ink-on-paper); display:flex; gap:var(--sp-5); flex-wrap:wrap;">'
    '<span>Fink · present</span>'
    '<span>Lasair-LSST · present</span>'
    '<span>ALeRCE · not observed</span>'
    "</div>"
    f"{mpc_html}"
    f"{notes_html}"
    "</div>",
    unsafe_allow_html=True,
)


# ---- Decision action bar -------------------------------------------------

def _decision_bar_html(disabled: bool = False) -> str:
    disabled_cls = " is-disabled" if disabled else ""
    qs_base = f"entry_id={entry_id}"
    return f"""
<div class="decision-bar" style="margin-top: var(--sp-6); padding: var(--sp-5); background: var(--surface-paper); border-radius: var(--radius-lg);">
  <a class="btn-decision btn-accept{disabled_cls}" href="?{qs_base}&action=accept">ACCEPT</a>
  <a class="btn-decision btn-defer{disabled_cls}" href="?{qs_base}&action=defer">DEFER</a>
  <a class="btn-decision btn-reject{disabled_cls}" href="?{qs_base}&pending=reject">REJECT</a>
  <a class="btn-decision btn-promote{disabled_cls}" href="?{qs_base}&pending=promote">PROMOTE TO CANDIDATE</a>
</div>
"""


if not is_readonly:
    st.markdown(_decision_bar_html(), unsafe_allow_html=True)

    # Reject form ------------------------------------------------------------
    if pending == "reject":
        st.markdown(
            '<div class="card-paper u-mt-4" style="padding: var(--sp-5);">'
            '<div class="h3" style="color:var(--ink-on-paper); font-family: var(--font-display); font-weight:500; margin-bottom: var(--sp-3);">Reject — select reason</div>'
            '<div class="body-sm" style="color:var(--ink-on-paper-muted); margin-bottom: var(--sp-4);">'
            "A reason is required (PRD §10 null-hypothesis checklist)."
            "</div>",
            unsafe_allow_html=True,
        )
        reason_keys = [k for k, _ in NULL_TEST_REASONS]
        reason_labels = {k: lab for k, lab in NULL_TEST_REASONS}
        with st.form("reject_form", clear_on_submit=False):
            reason = st.selectbox(
                "Reason",
                reason_keys,
                format_func=lambda k: reason_labels[k],
            )
            note = st.text_area(
                "Note (optional unless reason is Other)",
                placeholder="One-line rationale for the archive record…",
            )
            col_cancel, col_submit = st.columns([1, 1])
            with col_cancel:
                cancel = st.form_submit_button("Cancel")
            with col_submit:
                confirm = st.form_submit_button("Confirm reject")
            if cancel:
                st.query_params.clear()
                st.query_params["entry_id"] = str(entry_id)
                st.rerun()
            if confirm:
                if reason == "other" and not note.strip():
                    st.error("A note is required when the reason is Other.")
                else:
                    full_note = f"{reason_labels[reason]}"
                    if note.strip():
                        full_note += " — " + note.strip()
                    db.append_decision(conn, entry_id, "reject", full_note)
                    st.query_params.clear()
                    st.query_params["entry_id"] = str(entry_id)
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # Promote form -----------------------------------------------------------
    if pending == "promote":
        st.markdown(
            '<div class="card-paper u-mt-4" style="padding: var(--sp-5);">'
            '<div class="h3" style="color:var(--ink-on-paper); font-family: var(--font-display); font-weight:500; margin-bottom: var(--sp-3);">Promote to candidate — attach follow-up evidence</div>'
            '<div class="body-sm" style="color:var(--ink-on-paper-muted); margin-bottom: var(--sp-4);">'
            "Promotion requires independent follow-up astrometry per ADR-0005 Stage B. "
            "Enter an MPC designation, URL, or local file reference."
            "</div>",
            unsafe_allow_html=True,
        )
        with st.form("promote_form", clear_on_submit=False):
            evidence = st.text_input(
                "Evidence reference",
                placeholder="e.g. MPEC 2026-XNN, ATEL #XXXXX, /local/path/astrometry.ades",
            )
            note = st.text_area(
                "Confirmation note",
                placeholder="Refit with extended arc held signature within σ. …",
            )
            col_cancel, col_submit = st.columns([1, 1])
            with col_cancel:
                cancel = st.form_submit_button("Cancel")
            with col_submit:
                confirm = st.form_submit_button("Promote to candidate")
            if cancel:
                st.query_params.clear()
                st.query_params["entry_id"] = str(entry_id)
                st.rerun()
            if confirm:
                if not evidence.strip():
                    st.error("Evidence reference is required to promote.")
                else:
                    full_note = f"evidence: {evidence.strip()}"
                    if note.strip():
                        full_note += " — " + note.strip()
                    db.append_decision(conn, entry_id, "promote", full_note)
                    st.query_params.clear()
                    st.query_params["entry_id"] = str(entry_id)
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
else:
    # Read-only banner for archived entries ----------------------------------
    status_lower = (entry.get("status") or "").lower()
    banner_bg = {
        "accept": "var(--decision-accept)",
        "reject": "var(--decision-reject)",
        "promoted": "var(--decision-promote)",
    }.get(status_lower, "var(--divider)")
    decisions_history = db.entry_decisions(conn, entry_id)
    last_decision = decisions_history[-1] if decisions_history else None
    decision_note = last_decision["note"] if last_decision else ""
    decided_utc = last_decision["decided_utc"] if last_decision else ""
    decision_type_label = last_decision["decision"].upper() if last_decision else ""

    st.markdown(
        f'<div class="card-paper u-mt-6" style="padding: var(--sp-5); border-left: 4px solid {banner_bg};">'
        f'<div class="data-label data-label--paper">Decision — archived</div>'
        f'<div class="mono u-mt-4" style="color:var(--ink-on-paper);">{decision_type_label} · {html.escape(decided_utc)}</div>'
        f'<div class="body u-mt-4" style="color:var(--ink-on-paper);">{html.escape(decision_note)}</div>'
        "</div>",
        unsafe_allow_html=True,
    )
