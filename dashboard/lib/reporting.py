"""Per-entry 'What to do with this flag' guidance (ADR-0018 Panel 3).

Turns a watch-list entry into plain-English advice for a hobbyist
operator: why this might be new, what would make it real (the two-stage
gate in human language), where to seek independent follow-up, what
credit looks like, and a 'don't-post' reminder.

Language discipline (ADR-0005, reaffirmed in ADR-0018): never the words
'discovery', 'candidate', 'confirmed' applied to a watch-list entry.
Always hedged: 'might', 'could', 'would make it real', 'would be'.
The unit tests for this module assert the discipline holds.
"""

from __future__ import annotations

import html as _html
from typing import Any


__all__ = ["panel_3_html"]


def _esc(x: Any) -> str:
    return _html.escape("" if x is None else str(x))


# ---- RA/DEC formatting ----------------------------------------------------

def _ra_to_hms(ra_deg: float | None) -> str:
    if ra_deg is None:
        return "—"
    try:
        d = float(ra_deg) % 360.0
    except (TypeError, ValueError):
        return "—"
    hours = d / 15.0
    h = int(hours)
    m_full = (hours - h) * 60.0
    m = int(m_full)
    s = (m_full - m) * 60.0
    return f"{h:02d}h {m:02d}m {s:05.2f}s"


def _dec_to_dms(dec_deg: float | None) -> str:
    if dec_deg is None:
        return "—"
    try:
        v = float(dec_deg)
    except (TypeError, ValueError):
        return "—"
    sign = "+" if v >= 0 else "-"
    a = abs(v)
    d = int(a)
    m_full = (a - d) * 60.0
    m = int(m_full)
    s = (m_full - m) * 60.0
    return f"{sign}{d:02d}° {m:02d}' {s:04.1f}\""


# ---- Panel 3 sections -----------------------------------------------------

def _why_new(entry: dict[str, Any]) -> str:
    first = (entry.get("created_utc") or "")[:19].replace("T", " ")
    n_obs = int(entry.get("n_obs") or 0)
    mpc = (entry.get("mpc_crossmatch") or "").strip()
    mpc_miss = not mpc or any(
        tok in mpc.lower() for tok in ("no match", "miss", "none", "unknown")
    )

    mpc_line = (
        '<li><span class="bullet-dot bullet-dot--ok"></span>'
        '<p>No match within <strong>30 arcminutes</strong> in MPC\'s catalogue — '
        'this body isn\'t a known numbered asteroid or comet.</p></li>'
        if mpc_miss else
        '<li><span class="bullet-dot bullet-dot--warn"></span>'
        f'<p>MPC cross-match note: <strong>{_esc(mpc)}</strong>.</p></li>'
    )

    return (
        '<div class="reporting-card">'
        '<div class="reporting-card__head">'
        '<span class="reporting-card__num">01</span>'
        '<span class="reporting-card__title">Why this might be new</span>'
        '</div>'
        '<ul class="reporting-card__list">'
        f'{mpc_line}'
        '<li><span class="bullet-dot bullet-dot--ok"></span>'
        f'<p>Your pipeline <strong>first connected</strong> these {n_obs} '
        f'detections into one tracklet on <strong>{_esc(first)} UTC</strong>.</p></li>'
        '<li><span class="bullet-dot bullet-dot--muted"></span>'
        '<p>Individual detections were public in Rubin\'s alert stream, '
        'but no one else has linked them yet.</p></li>'
        '</ul></div>'
    )


def _what_real() -> str:
    return (
        '<div class="reporting-card">'
        '<div class="reporting-card__head">'
        '<span class="reporting-card__num">02</span>'
        '<span class="reporting-card__title">What would make it real</span>'
        '</div>'
        '<p class="reporting-card__body">'
        'A new Solar System object needs <strong>another observatory to see '
        'it independently</strong>, with positions accurate enough to refine '
        'the orbit. Until that second observation lands, this is a watch-list '
        'flag — not a confirmed find.'
        '</p>'
        '<div class="reporting-inset">'
        '<span class="reporting-inset__label">In plain English</span>'
        '<p>Rubin saw it. Someone else needs to point a different telescope '
        'at the same patch of sky, see the same object, and report it to the '
        'Minor Planet Center.</p>'
        '</div>'
        '</div>'
    )


# Follow-up channels — stable three-item list. Add a fourth only when it
# fits the hobbyist-first framing (no pay-walled or insider-only channels).
_CHANNELS = (
    (
        "A",
        "MPC NEO Confirmation Page",
        "Use when the object's orbit could bring it near Earth. Fastest "
        "follow-up path — seen by professional and amateur observers "
        "worldwide.",
        "https://minorplanetcenter.net/iau/NEO/toconfirm_tabular.html",
        "minorplanetcenter.net",
    ),
    (
        "B",
        "The Astronomer's Telegram (ATel)",
        "Public request for follow-up on a transient or anomalous object. "
        "Appropriate when you want the broad community to help, not a "
        "single observer.",
        "https://astronomerstelegram.org/",
        "astronomerstelegram.org",
    ),
    (
        "C",
        "BAA Comet Section",
        "Amateur follow-up network focused on comets. Useful for "
        "multi-night cadence and light-curve work once a candidate is up.",
        "https://britastro.org/sections/comet",
        "britastro.org/comet",
    ),
)


def _how_to_get_eyes(entry: dict[str, Any], first_detection: dict | None) -> str:
    rows = "".join(
        '<div class="channel-row">'
        f'<span class="channel-row__letter">{letter}.</span>'
        '<div class="channel-row__body">'
        f'<span class="channel-row__title">{_esc(title)}</span>'
        f'<span class="channel-row__desc">{_esc(desc)}</span>'
        '</div>'
        f'<a class="channel-row__url" href="{_esc(url)}" target="_blank" '
        f'rel="noopener">{_esc(shown)} ↗</a>'
        '</div>'
        for letter, title, desc, url, shown in _CHANNELS
    )

    if first_detection:
        ra_hms = _ra_to_hms(first_detection.get("ra"))
        dec_dms = _dec_to_dms(first_detection.get("dec"))
        mjd = first_detection.get("mjd")
        epoch = f"MJD {float(mjd):.4f}" if mjd is not None else "—"
    else:
        ra_hms = dec_dms = epoch = "—"
    ephem = f"RA {ra_hms} · DEC {dec_dms} · epoch {epoch}"

    return (
        '<div class="reporting-card reporting-card--wide">'
        '<div class="reporting-card__head">'
        '<span class="reporting-card__num">03</span>'
        '<span class="reporting-card__title">How to get eyes on it</span>'
        '</div>'
        f'<div class="channel-list">{rows}</div>'
        '<div class="ephemeris-bar">'
        '<span class="ephemeris-bar__label">EPHEMERIS</span>'
        f'<code class="ephemeris-bar__coords">{_esc(ephem)}</code>'
        f'<a class="ephemeris-bar__copy" href="#copy" '
        f'data-copy="{_esc(ephem)}">COPY COORDS</a>'
        '</div></div>'
    )


def _credit() -> str:
    return (
        '<div class="reporting-card reporting-card--credit">'
        '<div class="reporting-card__head">'
        '<span class="reporting-card__num">04</span>'
        '<span class="reporting-card__title">What credit looks like</span>'
        '</div>'
        '<p class="reporting-card__body">'
        'If this becomes a real find, <strong>MPC credit goes to Rubin '
        'and the observatory that does the follow-up</strong>, not to this '
        'pipeline or to you as its operator. That\'s how the clearinghouse '
        'has always worked.'
        '</p>'
        '<p class="reporting-card__body">'
        'What your flag does get is the thing that actually matters: '
        '<strong>being first to connect these detections</strong> and '
        'point a second observatory at the right patch of sky. That\'s '
        'how follow-up starts.'
        '</p>'
        '</div>'
    )


def _dont_post() -> str:
    # Reputation-hygiene invariant (ADR-0018 new obligation).
    return (
        '<div class="dont-post-card">'
        '<div class="dont-post-card__head">'
        '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" '
        'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        '<path d="M7 1.5L13 12H1L7 1.5Z" stroke="#F87171" '
        'stroke-width="1.4" stroke-linejoin="round"/>'
        '<path d="M7 5.5V8.5" stroke="#F87171" stroke-width="1.4" '
        'stroke-linecap="round"/>'
        '<circle cx="7" cy="10.3" r="0.7" fill="#F87171"/>'
        '</svg>'
        '<span>Don\'t post this</span>'
        '</div>'
        '<p class="dont-post-card__body">Don\'t call this a find on social '
        'media. It isn\'t one yet — not until a second observatory sees it '
        'and the orbit refines.</p>'
        '<p class="dont-post-card__aside">Loose claims that don\'t pan out '
        'hurt the next flag\'s chances of being taken seriously.</p>'
        '</div>'
    )


# ---- Public --------------------------------------------------------------

def panel_3_html(
    entry: dict[str, Any],
    first_detection: dict | None = None,
) -> str:
    """Render the full 'What to do with this flag' band.

    Layout: amber rule, intro line, 2-col (Why new + What real),
    full-width How-to-get-eyes with ephemeris bar, 2-col (Credit +
    Don't-post). Caller inserts this into the Tonight canvas after the
    narrative/evidence bands and before the decision bar.
    """
    return (
        '<div class="reporting-band">'
        '<div class="amber-rule">'
        '<span class="amber-rule__line amber-rule__line--left"></span>'
        '<span class="amber-rule__label">What to do with this flag</span>'
        '<span class="amber-rule__line amber-rule__line--right"></span>'
        '</div>'
        '<p class="reporting-intro">This flag is <strong>not a find</strong> '
        '— it\'s a pointer. Here\'s how to turn it into one, and what '
        'happens if you do.</p>'
        '<div class="reporting-grid reporting-grid--2">'
        f'{_why_new(entry)}'
        f'{_what_real()}'
        '</div>'
        f'{_how_to_get_eyes(entry, first_detection)}'
        '<div class="reporting-grid reporting-grid--credit">'
        f'{_credit()}'
        f'{_dont_post()}'
        '</div>'
        '</div>'
    )
