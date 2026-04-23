"""Reusable HTML-as-Streamlit components per docs/ux/design-system.md §6.

Class names align with dashboard/static/theme.css (the design-system
implementation). Functions return HTML strings to pass into
st.markdown(..., unsafe_allow_html=True).

Business logic lives in dashboard.lib.db — components have none.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
from typing import Any

from .mockimg import (
    OrbitParams,
    cutout_b64,
    light_curve_svg,
    orbit_svg,
    sparkline_svg,
)
from .narrative import (
    ORBITAL_ELEMENT_GLOSSARY,
    Hypothesis,
    Trigger,
    WhyFlagged,
    generate_hypotheses,
    generate_why_flagged,
)
from .theme import kind_pill, status_pill


# -------- Data-source banner ----------------------------------------------

def data_source_banner_html(info: dict[str, Any]) -> str:
    """Amber banner at the top of a page when orbit-fit / linking is mock.

    Renders nothing when on the live DB with real binaries, or on the demo
    DB (the demo already self-identifies via the sidebar footer tag). Only
    fires when ``is_live`` is True AND at least one of the two pipeline
    stages ran in mock mode — that's the case that can mislead a reader.
    """
    if not info.get("is_live"):
        return ""
    mock_fit = bool(info.get("any_mock_fit"))
    mock_link = bool(info.get("any_mock_linker"))
    if not (mock_fit or mock_link):
        return ""
    parts = []
    if mock_link:
        parts.append("<strong>heliolinc3d:</strong> mock")
    if mock_fit:
        parts.append("<strong>find_orb:</strong> mock")
    joined = "  ·  ".join(parts)
    return (
        '<div class="mock-banner">'
        '<span class="mock-banner__label">ORBIT/LINK PATH</span>'
        f'<span class="mock-banner__body">{joined} — orbits and tracklets on this page are '
        '<em>placeholder</em> outputs, not scientifically valid. '
        'Install the binaries (WSL2 on Windows) to go live.</span>'
        '</div>'
    )


# -------- Page header ------------------------------------------------------

def page_header_html(
    title: str,
    now_line: str | None = None,
    meta_line: str | None = None,
) -> str:
    meta_bits = []
    if now_line:
        meta_bits.append(f'<div class="now">{html.escape(now_line)}</div>')
    if meta_line:
        meta_bits.append(f'<div>{html.escape(meta_line)}</div>')
    meta = "".join(meta_bits)
    return (
        '<div class="rh-page-header">'
        f'<div class="title">{html.escape(title)}</div>'
        f'<div class="meta">{meta}</div>'
        "</div>"
    )


# -------- Summary tile (Tonight) -------------------------------------------

def summary_tile(
    label: str,
    value: str,
    breakdown: str | None = None,
    zero_state: bool = False,
) -> str:
    cls = "tile-glass summary-tile"
    if zero_state:
        cls += " is-zero"
    breakdown_html = f'<div class="breakdown">{html.escape(breakdown)}</div>' if breakdown else ""
    return (
        f'<div class="{cls}">'
        f'  <div class="label">{html.escape(label)}</div>'
        f'  <div class="value">{html.escape(value)}</div>'
        f'  <div class="value-underline"></div>'
        f"  {breakdown_html}"
        "</div>"
    )


def hero_tonight_html(
    total_new: int,
    new_dark_comet: int,
    new_iso: int,
    verdict_line: str,
    secondary: str = "",
) -> str:
    """Hero block for the Tonight page — oversized mono numeric in amber."""
    is_zero = total_new == 0
    zero_cls = " is-zero" if is_zero else ""
    # Always at least two digits to give the numeral typographic weight
    numeric = f"{total_new:02d}"
    breakdown_parts = []
    if new_dark_comet:
        breakdown_parts.append(f"{new_dark_comet:02d} DARK COMET")
    if new_iso:
        breakdown_parts.append(f"{new_iso:02d} ISO")
    breakdown = "  ·  ".join(breakdown_parts) or "QUIET"
    return (
        f'<section class="hero-tonight{zero_cls}">'
        f'  <div class="hero-numeric">{numeric}</div>'
        f'  <div class="hero-body">'
        f'    <div class="hero-label">WATCH LIST · NEW SINCE LAST VISIT</div>'
        f'    <div class="hero-verdict">{html.escape(verdict_line)}</div>'
        f'    <div class="hero-breakdown">{html.escape(breakdown)}{"  ·  " + html.escape(secondary) if secondary else ""}</div>'
        f"  </div>"
        f"</section>"
    )


def telemetry_bar_html(segments: list[tuple[str, str, str]]) -> str:
    """Top-of-page status bar. Each segment = (state, label, value) where state
    is one of 'ok', 'warn', 'err', or '' for neutral."""
    parts = []
    for state, label, value in segments:
        cls = f"seg {state}" if state else "seg"
        val_html = f'<span class="val">{html.escape(value)}</span>' if value else ""
        parts.append(
            f'<span class="{cls}">{html.escape(label)}{" · " if value else ""}{val_html}</span>'
        )
    return '<div class="telemetry-bar">' + "".join(parts) + "</div>"


def sparkline_tile(label: str, values: list[float], current_text: str = "") -> str:
    svg = sparkline_svg(values)
    return (
        '<div class="tile-glass summary-tile">'
        f'<div class="label">{html.escape(label)}</div>'
        f'<div class="sparkline-body">{svg}</div>'
        f'<div class="breakdown">{html.escape(current_text)}</div>'
        "</div>"
    )


# -------- Watch-list row ---------------------------------------------------

def _shorten_mpc(mpc: str, width: int = 28) -> str:
    """Clip MPC text at word boundary, not mid-token. Returns '—' for 'no match'."""
    if not mpc or mpc == "—":
        return "—"
    low = mpc.lower()
    if "no match" in low:
        return "—"
    if len(mpc) <= width:
        return mpc
    # break at last space before the width limit
    cut = mpc.rfind(" ", 0, width)
    if cut < width // 2:
        cut = width - 1
    return mpc[:cut] + "…"


def _short_whatsweird(entry: dict[str, Any]) -> str:
    """One-line 'what's weird' summary for watch-list row secondary line."""
    try:
        why = generate_why_flagged(entry)
    except Exception:
        return ""
    return why.headline.lower()


def watch_list_row_html(entry: dict[str, Any]) -> str:
    kind = entry.get("category", "")
    kind_css = kind.replace("_", "-")
    internal = f"wle-0x{entry['entry_id']:08x}"
    date = (entry.get("created_utc") or "")[:10]
    n_obs = entry.get("n_obs") or 0
    n_nights = entry.get("num_nights") or 0
    mpc_raw = entry.get("mpc_crossmatch") or ""
    fit_rms = entry.get("fit_rms")
    rms_text = f"rms {fit_rms:.2f}″" if isinstance(fit_rms, (int, float)) else ""
    status = (entry.get("status") or "new").lower()

    if status not in {"new", "defer", "deferred"}:
        status = "new"

    mpc_text = _shorten_mpc(mpc_raw)
    mpc_mark = ""
    if mpc_text != "—":
        mpc_mark = " is-mpc-match"

    badge_label = "DARK COMET" if kind == "dark_comet" else "ISO"
    href = f"/Candidate_Detail?entry_id={entry['entry_id']}"

    whatsweird = _short_whatsweird(entry)

    return (
        f'<a class="wle-row{mpc_mark}" href="{href}" target="_self">'
        f'  <div class="wle-row__main">'
        f'    <span class="kind-dot kind-dot--{kind_css}"></span>'
        f'    <span class="kind-badge kind-badge--{kind_css}">{badge_label}</span>'
        f'    <span class="wle-id">{internal}</span>'
        f'    <span class="wle-meta">{html.escape(date)}</span>'
        f'    <span class="wle-meta">{n_obs} det / {n_nights}n</span>'
        f'    <span class="wle-meta">MPC: {html.escape(mpc_text)}</span>'
        f'    <span class="wle-meta">{rms_text}</span>'
        f'    <span class="wle-meta">{status_pill(status)}</span>'
        f'  </div>'
        f'  <div class="wle-row__whatsweird">{html.escape(whatsweird)}</div>'
        "</a>"
    )


# -------- Null-hypothesis test list ---------------------------------------

_NULL_TEST_LABELS = [
    ("known_sso_match", "No known-SSO match within tolerance"),
    ("cometary_outgassing_consistent", "Non-grav not typical of cometary outgassing"),
    ("image_artifact", "No image artifact / bad subtraction"),
    ("streak_residual", "No streak / streak-endpoint residual"),
    ("short_arc_ambiguity", "Tracklet quality nominal"),
    ("instrument_systematic", "No instrument systematic"),
    ("broker_flag_drift", "Broker flags stable since ingest"),
]


def _classify_null_test(raw: str | None) -> tuple[str, str, str, str]:
    """Return (glyph, row_cls, state_label, detail) for a raw test value.

    Demo data carries values like 'pass', 'fail', 'warn', or 'suspicious —
    long detail text'. We treat anything starting with pass/fail/warn/
    suspicious/pending as a state keyword; the rest becomes detail text.
    """
    if not raw:
        return "○", "nht-pending", "pending", ""
    s = raw.strip()
    lower = s.lower()
    head = lower.split()[0].rstrip("—-:.,") if lower else ""
    detail = ""
    if "—" in s or " - " in s:
        # Split at the first em-dash or hyphen-space for detail
        for sep in ["—", " - "]:
            if sep in s:
                head_str, _, detail = s.partition(sep)
                head = head_str.strip().lower().split()[0] if head_str.strip() else head
                detail = detail.strip()
                break
    if head in {"pass", "ok"}:
        return "✓", "nht-pass", "pass", detail
    if head in {"fail", "failed", "failure"}:
        return "✗", "nht-fail", "fail", detail or s
    if head in {"warn", "warning", "suspicious", "amber"}:
        # '△' signals attention, not alarm (design-system §8 anti-pattern #2).
        return "△", "nht-warn", "warn", detail or (s if head != "warn" else "")
    # Treat any unrecognized non-empty value as informational pending with detail
    return "○", "nht-pending", "pending", s


def null_hypothesis_panel(tests: dict[str, str]) -> str:
    items = []
    for key, label in _NULL_TEST_LABELS:
        glyph, row_cls, _state, detail = _classify_null_test(tests.get(key))
        detail_html = (
            '<div class="body-sm" style="color: var(--ink-on-paper-muted); '
            'margin-left: 22px; margin-top: 2px; font-style: italic;">'
            f"{html.escape(detail)}</div>"
        ) if detail else ""
        items.append(
            f'<li class="{row_cls}">'
            f'<span class="nht-mark">{glyph}</span>'
            f'<span>{html.escape(label)}</span>'
            f"</li>"
            f"{detail_html}"
        )
    return (
        '<div class="data-label data-label--paper">Null-hypothesis tests (PRD §10)</div>'
        '<ul class="nht-list">' + "".join(items) + "</ul>"
    )


# -------- Orbit fit block --------------------------------------------------

def orbit_fit_block(entry: dict[str, Any]) -> str:
    """Orbit fit rendered as a two-column grid: value + plain-language annotation.

    Each row explains what the symbol means in a way a hobbyist astronomer can
    scan without remembering their undergrad mechanics. Glossary lives in
    narrative.ORBITAL_ELEMENT_GLOSSARY.
    """
    def fmt(v: Any, unit: str = "", prec: int = 3) -> str:
        if v is None:
            return "—"
        try:
            return f"{float(v):.{prec}f}{unit}"
        except (TypeError, ValueError):
            return "—"

    def sci(v: Any, sigma: Any, unit: str) -> str:
        if v is None:
            return "—"
        try:
            s = f"{float(v):.2e}"
            if sigma is not None:
                s += f" ± {float(sigma):.1e}"
            return s + (f" {unit}" if unit else "")
        except (TypeError, ValueError):
            return "—"

    sigma_e = entry.get("sigma_e")
    e_txt = fmt(entry.get("e"), "", 3)
    if sigma_e:
        e_txt += f"  ± {float(sigma_e):.3f}"

    rows: list[tuple[str, str, str]] = [
        ("a",   fmt(entry.get('a_au'), ' AU', 2),           ORBITAL_ELEMENT_GLOSSARY["a"]),
        ("e",   e_txt,                                       ORBITAL_ELEMENT_GLOSSARY["e"]),
        ("i",   fmt(entry.get('incl_deg'), '°', 2),          ORBITAL_ELEMENT_GLOSSARY["i"]),
        ("q",   fmt(entry.get('perihelion_au'), ' AU', 2),   ORBITAL_ELEMENT_GLOSSARY["q"]),
        ("Q",   fmt(entry.get('aphelion_au'), ' AU', 2),     ORBITAL_ELEMENT_GLOSSARY["Q"]),
        ("A1",  sci(entry.get('A1'), entry.get('sigma_A1'), 'AU/d²'),  ORBITAL_ELEMENT_GLOSSARY["A1"]),
        ("A2",  sci(entry.get('A2'), entry.get('sigma_A2'), 'AU/d²'),  ORBITAL_ELEMENT_GLOSSARY["A2"]),
        ("A3",  sci(entry.get('A3'), entry.get('sigma_A3'), 'AU/d²'),  ORBITAL_ELEMENT_GLOSSARY["A3"]),
        ("rms", fmt(entry.get('fit_rms'), ' arcsec', 3),     ORBITAL_ELEMENT_GLOSSARY["rms"]),
    ]

    row_html = "".join(
        f'<div class="orbit-fit__row">'
        f'<span class="orbit-fit__symbol">{html.escape(sym)}</span>'
        f'<span class="orbit-fit__value">{html.escape(value)}</span>'
        f'<span class="orbit-fit__gloss">{html.escape(gloss)}</span>'
        "</div>"
        for sym, value, gloss in rows
    )

    software = entry.get('software_version') or '—'
    n_obs = entry.get('n_obs') or '—'
    return (
        '<div class="data-label data-label--paper">Orbit fit — find_orb, Marsden A1/A2/A3</div>'
        f'<div class="orbit-fit-grid">{row_html}</div>'
        f'<div class="orbit-fit__provenance">'
        f'{n_obs} detections · {html.escape(str(software))}'
        f"</div>"
    )


# -------- Cutouts strip ---------------------------------------------------

def why_flagged_panel_html(why: WhyFlagged) -> str:
    """The narrative panel at the top of Candidate Detail: 'what's weird about this'."""
    paragraphs_html = "".join(
        f'<p class="why-flagged__para">{html.escape(p)}</p>'
        for p in why.summary_paragraphs
    )
    trigger_rows = []
    for t in why.triggers:
        glyph = "✓" if t.passed else "△"
        row_cls = "why-flagged__trigger is-pass" if t.passed else "why-flagged__trigger is-warn"
        threshold_html = (
            f'<span class="why-flagged__trigger-threshold">{html.escape(t.threshold)}</span>'
            if t.threshold else ""
        )
        trigger_rows.append(
            f'<li class="{row_cls}">'
            f'<span class="why-flagged__trigger-glyph">{glyph}</span>'
            f'<span class="why-flagged__trigger-label">{html.escape(t.label)}</span>'
            f'<span class="why-flagged__trigger-value">{html.escape(t.observed)}</span>'
            f'{threshold_html}'
            "</li>"
        )
    triggers_html = (
        '<div class="why-flagged__triggers-title">EVIDENCE BEHIND THE FLAG</div>'
        f'<ul class="why-flagged__triggers">{"".join(trigger_rows)}</ul>'
        if trigger_rows else ""
    )
    return (
        '<section class="why-flagged">'
        '<div class="why-flagged__label">WHAT\'S WEIRD ABOUT THIS</div>'
        f'<h2 class="why-flagged__headline">{html.escape(why.headline)}</h2>'
        f'<div class="why-flagged__body">{paragraphs_html}</div>'
        f'{triggers_html}'
        "</section>"
    )


_LIKELIHOOD_LABELS = {
    "leading":    ("LEADING",    "hyp-leading"),
    "plausible":  ("PLAUSIBLE",  "hyp-plausible"),
    "unlikely":   ("UNLIKELY",   "hyp-unlikely"),
    "systematic": ("SYSTEMATIC", "hyp-systematic"),
}


def hypotheses_panel_html(hypotheses: list[Hypothesis]) -> str:
    """Ranked hypothesis list. First one (leading) is open by default; others
    collapsed via native <details>. No JS."""
    if not hypotheses:
        return ""

    def _hypothesis_card(h: Hypothesis, is_first: bool) -> str:
        label, pill_cls = _LIKELIHOOD_LABELS.get(h.likelihood, ("—", ""))

        def _bullets(items: list[str], title: str) -> str:
            if not items:
                return ""
            lis = "".join(f"<li>{html.escape(x)}</li>" for x in items)
            return (
                f'<div class="hyp__bullets-title">{html.escape(title)}</div>'
                f'<ul class="hyp__bullets">{lis}</ul>'
            )

        open_attr = " open" if is_first else ""
        return (
            f'<details class="hyp-card"{open_attr}>'
            f'<summary class="hyp-card__summary">'
            f'<span class="hyp-card__pill {pill_cls}">{html.escape(label)}</span>'
            f'<span class="hyp-card__name">{html.escape(h.name)}</span>'
            f'<span class="hyp-card__tagline">{html.escape(h.tagline)}</span>'
            f'<span class="hyp-card__chevron">▾</span>'
            f'</summary>'
            f'<div class="hyp-card__body">'
            f'<p class="hyp-card__desc">{html.escape(h.description)}</p>'
            f'{_bullets(h.supports, "SUPPORTS")}'
            f'{_bullets(h.would_confirm, "WOULD CONFIRM")}'
            f'{_bullets(h.would_refute, "WOULD REFUTE")}'
            f'</div>'
            f'</details>'
        )

    cards = "".join(_hypothesis_card(h, i == 0) for i, h in enumerate(hypotheses))
    return (
        '<section class="hypotheses">'
        '<div class="hypotheses__label">WHAT IT COULD BE</div>'
        f'<div class="hypotheses__list">{cards}</div>'
        "</section>"
    )


def cutouts_strip_html(entry_id: int, n_epochs: int = 4) -> str:
    stamps = ("science", "template", "difference")
    rows = []
    for det_idx in range(min(n_epochs, 5)):
        mjd_fake = 60832.0 + det_idx * 1.05
        col_cells = []
        for stamp in stamps:
            src = cutout_b64(entry_id, det_idx, stamp)
            col_cells.append(
                '<div class="cutout">'
                f'<div class="img" style="background-image:url({src});"></div>'
                f'<div class="caption">{stamp[:4]} · mjd {mjd_fake:.2f} · r</div>'
                "</div>"
            )
        rows.append(
            '<div style="display:flex; gap:var(--sp-3); margin-bottom:var(--sp-3);">'
            + "".join(col_cells) + "</div>"
        )
    note = (
        '<div class="mono-sm" style="color:var(--ink-on-paper-muted); margin-top:var(--sp-3);">'
        'Cutouts are <strong>synthetic</strong> in demo mode — real alert cutouts will render here '
        "once the live stream is connected.</div>"
    )
    return (
        '<div class="data-label data-label--paper">Cutouts (science · template · difference)</div>'
        '<div style="margin-top:var(--sp-3);">' + "".join(rows) + note + "</div>"
    )


# -------- Orbit frame + light curve frame ---------------------------------

def plot_frame_html(title: str, caption: str, svg_body: str) -> str:
    return (
        '<div class="plot-frame">'
        f'<div class="plot-head"><span>{html.escape(title)}</span><span></span></div>'
        f'<div>{svg_body}</div>'
        f'<div class="plot-caption">{html.escape(caption)}</div>'
        "</div>"
    )


def orbit_frame_html(entry: dict[str, Any]) -> str:
    params = OrbitParams(
        a_au=float(entry.get("a_au") or 2.0),
        e=float(entry.get("e") or 0.2),
        incl_deg=float(entry.get("incl_deg") or 0.0),
        perihelion_au=entry.get("perihelion_au"),
        aphelion_au=entry.get("aphelion_au"),
        category=entry.get("category") or "dark_comet",
    )
    svg = orbit_svg(params)
    peri = f"{params.perihelion_au:.2f}" if params.perihelion_au else "—"
    caption = f"a={params.a_au:+.2f}  e={params.e:.3f}  i={params.incl_deg:.1f}°  q={peri} AU"
    return plot_frame_html("orbit (ecliptic, top-down)", caption, svg)


def light_curve_frame_html(entry: dict[str, Any], detections: list[dict[str, Any]]) -> str:
    svg = light_curve_svg(entry["entry_id"], detections)
    bands = sorted({d.get("band", "r") for d in detections})
    caption = f"bands: {' '.join(bands) or '—'}   · {len(detections)} detections"
    return plot_frame_html("light curve", caption, svg)


# -------- Empty state -----------------------------------------------------

_EMPTY_QUOTES = [
    ("What the survey does not find is also a result.", "after Wright et al. 2018"),
    ("The expected output of a careful search is silence, most nights.", "field-log maxim"),
    ("Null results have earned their place in the notebook.", "Sheikh (2020), Nine Axes of Merit"),
    ("Dark comets are quiet for the same reason deep wells are: they hide a depth.", "after Seligman et al. 2023"),
    ("Absence of a signal is not absence of sky.", ""),
]


def _deterministic_quote(key: str) -> tuple[str, str]:
    h = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16)
    return _EMPTY_QUOTES[h % len(_EMPTY_QUOTES)]


def _constellation_svg(seed_key: str) -> str:
    h = int(hashlib.sha256(seed_key.encode("utf-8")).hexdigest(), 16)
    n = 7 + (h % 4)
    pts = []
    rng = h
    for _ in range(n):
        rng = (rng * 1103515245 + 12345) & 0x7FFFFFFF
        x = 30 + (rng % 240)
        rng = (rng * 1103515245 + 12345) & 0x7FFFFFFF
        y = 20 + (rng % 60)
        pts.append((x, y))
    lines = [
        f'<line x1="{pts[i][0]}" y1="{pts[i][1]}" x2="{pts[i+1][0]}" y2="{pts[i+1][1]}" '
        f'stroke="currentColor" stroke-width="0.8" opacity="0.55"/>'
        for i in range(len(pts) - 1)
    ]
    dots = [f'<circle cx="{x}" cy="{y}" r="1.6" fill="currentColor"/>' for x, y in pts]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="100" '
        'viewBox="0 0 300 100" class="constellation">'
        + "".join(lines + dots)
        + "</svg>"
    )


def empty_state_html(
    verdict: str,
    counts: str,
    provenance: str,
    seed_key: str | None = None,
) -> str:
    quote_text, quote_cite = _deterministic_quote(seed_key or verdict)
    svg = _constellation_svg(seed_key or verdict)
    cite = f" — {html.escape(quote_cite)}" if quote_cite else ""
    return (
        '<div class="empty-state">'
        f'{svg}'
        f'<div class="verdict">{html.escape(verdict)}</div>'
        f'<div class="counts">{html.escape(counts)}</div>'
        f'<div class="provenance">{html.escape(provenance)}</div>'
        f'<div class="quote">"{html.escape(quote_text)}"{cite}</div>'
        "</div>"
    )


# -------- Archive row -----------------------------------------------------

def archive_row_html(decision: dict[str, Any]) -> str:
    kind = decision.get("category", "")
    kind_css = kind.replace("_", "-")
    decision_type = decision.get("decision", "—")
    date = (decision.get("decided_utc") or "")[:10]
    internal = f"wle-0x{decision['entry_id']:08x}"
    note = decision.get("note") or ""
    note_short = note if len(note) <= 90 else note[:87] + "…"
    pill_map = {
        "accept":  '<span class="pill pill-accept">ACCEPTED</span>',
        "defer":   '<span class="pill pill-defer">DEFERRED</span>',
        "reject":  '<span class="pill pill-reject">REJECTED</span>',
        "promote": f'<span class="pill pill-candidate">CANDIDATE · {html.escape(date)}</span>',
    }
    pill = pill_map.get(decision_type, "")
    href = f"/Candidate_Detail?entry_id={decision['entry_id']}"
    badge_label = "DARK COMET" if kind == "dark_comet" else "ISO"
    return (
        f'<a class="wle-row wle-row--archive" href="{href}" target="_self">'
        f'  <div class="wle-row__main wle-row__main--archive">'
        f'    <span class="kind-dot kind-dot--{kind_css}"></span>'
        f'    <span class="kind-badge kind-badge--{kind_css}">{badge_label}</span>'
        f'    <span class="wle-id">{internal}</span>'
        f'    <span class="wle-meta">{html.escape(date)}</span>'
        f'    <span class="wle-meta wle-meta--pill">{pill}</span>'
        f'    <span class="wle-meta wle-meta--note">{html.escape(note_short)}</span>'
        f'  </div>'
        "</a>"
    )


# -------- Pipeline health sparkline widget --------------------------------

def health_sparkline_html(
    metric: str,
    values: list[float],
    current_text: str,
    health_state: str = "ok",
    threshold: float | None = None,
) -> str:
    from .theme import health_pill

    svg = sparkline_svg(values, threshold=threshold)
    return (
        '<div class="sparkline-wrap">'
        '<div class="sparkline-head">'
        f'<span class="metric">{html.escape(metric)}</span>'
        f'<span class="value">{html.escape(current_text)} {health_pill(health_state)}</span>'
        "</div>"
        f'<div>{svg}</div>'
        "</div>"
    )


# -------- Card wrappers ---------------------------------------------------

def card_dark_open() -> str:
    return '<div class="card-dark">'


def card_dark_close() -> str:
    return "</div>"


def card_paper_open() -> str:
    return '<div class="card-paper">'


def card_paper_close() -> str:
    return "</div>"


def soft_divider() -> str:
    return '<hr class="divider">'


def paper_divider() -> str:
    return '<hr class="divider-paper">'


# -------- Small helpers ----------------------------------------------------

def format_mjd(iso_datetime: str | None) -> str:
    if not iso_datetime:
        return "—"
    try:
        d = dt.datetime.fromisoformat(iso_datetime.replace("Z", "+00:00"))
    except ValueError:
        return iso_datetime
    mjd_at_unix_epoch = 40587.0
    mjd = mjd_at_unix_epoch + d.timestamp() / 86400.0
    return f"mjd {mjd:.2f}"
