"""Derive plain-language narrative and ranked hypotheses from a watch-list entry.

This module answers the two questions a hobbyist astronomer actually asks when
they open a watch-list entry:

    1. What's weird about this — why did the pipeline flag it?
    2. What could it plausibly be?

Narratives are computed from the existing entry data (orbit fit, null-test
results, MPC cross-match, kind). No new DB columns. The goal is to translate
numbers and gates into prose that teaches the reader the field's vocabulary
while they triage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---- Data classes --------------------------------------------------------

@dataclass
class Trigger:
    """One line of specific evidence that helped the pipeline decide."""
    label: str
    passed: bool
    observed: str        # e.g. "A1 = 1.4e-8 AU/d²"
    threshold: str = ""  # e.g. "threshold 1.0e-9"


@dataclass
class WhyFlagged:
    headline: str              # Short, punchy. E.g. "Persistent non-gravitational acceleration"
    summary_paragraphs: list[str]
    triggers: list[Trigger] = field(default_factory=list)


@dataclass
class Hypothesis:
    name: str                   # "Dark comet"
    tagline: str                # One-line summary you can scan
    likelihood: str             # 'leading' | 'plausible' | 'unlikely' | 'systematic'
    description: str            # 1–3 sentences of context
    supports: list[str] = field(default_factory=list)     # bullets from current data
    would_confirm: list[str] = field(default_factory=list)
    would_refute: list[str] = field(default_factory=list)


# ---- Helpers -------------------------------------------------------------

def _fmt_sci(x: Any) -> str:
    try:
        return f"{float(x):.2e}"
    except (TypeError, ValueError):
        return "—"


def _has_nongrav(entry: dict[str, Any]) -> tuple[bool, str | None, float | None]:
    """Return (flagged, which_term, magnitude). which_term ∈ {A1, A2, A3, None}."""
    best_term = None
    best_mag = 0.0
    for term in ("A1", "A2", "A3"):
        v = entry.get(term)
        try:
            mag = abs(float(v))
        except (TypeError, ValueError):
            continue
        if mag > best_mag:
            best_mag = mag
            best_term = term
    # Threshold per configs/thresholds-commissioning.yaml
    thresholds = {"A1": 1.0e-9, "A2": 1.0e-10, "A3": 1.0e-10}
    if best_term and best_mag > thresholds[best_term]:
        return True, best_term, best_mag
    return False, best_term, best_mag


def _ratio_over_threshold(entry: dict[str, Any]) -> float | None:
    ok, term, mag = _has_nongrav(entry)
    if not ok or term is None or mag is None:
        return None
    thresholds = {"A1": 1.0e-9, "A2": 1.0e-10, "A3": 1.0e-10}
    return mag / thresholds[term]


def _null_test_state(tests: dict[str, Any], key: str) -> tuple[str, str]:
    """Return (state, detail) where state ∈ {pass, fail, warn, pending}."""
    raw = (tests or {}).get(key)
    if not raw:
        return "pending", ""
    s = str(raw).strip()
    head = s.lower().split()[0].rstrip("—-:.,")
    detail = ""
    for sep in ("—", " - "):
        if sep in s:
            _, _, detail = s.partition(sep)
            detail = detail.strip()
            break
    if head in {"pass", "ok"}:
        return "pass", detail
    if head in {"fail", "failed"}:
        return "fail", detail or s
    if head in {"warn", "warning", "suspicious"}:
        return "warn", detail or s
    return "pending", s


def _is_short_arc(entry: dict[str, Any]) -> bool:
    """Short-arc tripwire per audit guidance: <4 nights OR <7 detections."""
    try:
        n_nights = int(entry.get("num_nights") or 0)
    except (TypeError, ValueError):
        n_nights = 0
    try:
        n_obs = int(entry.get("n_obs") or 0)
    except (TypeError, ValueError):
        n_obs = 0
    return n_nights < 4 or n_obs < 7


def _mock_fit_caveat(entry: dict[str, Any]) -> str:
    """Single trailing clause when orbit fit is a mock placeholder."""
    if str(entry.get("software_version", "") or "").startswith("mock"):
        return " (Orbit fit is placeholder; real find_orb not installed.)"
    return ""


# ---- Night lede ---------------------------------------------------------

def generate_night_lede(summary: dict[str, Any], cadence_phrase: str = "") -> str:
    """Return a one-sentence, sentence-case lede describing tonight's shape.

    ``summary`` is the dict from ``dashboard.lib.db.tonight_summary``.
    ``cadence_phrase`` is a short clause (e.g. "typical for this window",
    "yield in line with median") — when empty the clause is omitted.

    The lede stays ≤30 words, uses plain astronomer-hobbyist English, and
    never uses the banned ADR-0005 language ("discovery", "remarkable",
    "amazing"). Every count combination is handled and missing keys do
    not raise.

    >>> generate_night_lede({'new_total':0,'new_dark_comet':0,'new_iso':0,
    ...                      'alerts_ingested_last':50,'tracklets_linked_last':48})
    'Quiet night: 50 alerts ingested, 48 tracklets linked, nothing flagged for review.'

    >>> generate_night_lede({'new_total':1,'new_dark_comet':1,'new_iso':0,
    ...                      'alerts_ingested_last':50,'tracklets_linked_last':48},
    ...                     'yield in line with the 14-night median')
    'One dark-comet entry flagged tonight from 50 alerts and 48 tracklets, yield in line with the 14-night median.'

    >>> generate_night_lede({})
    'No pipeline run recorded yet — nothing to show tonight.'
    """
    s = summary or {}

    def _int(key: str) -> int:
        try:
            return int(s.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    alerts = _int("alerts_ingested_last")
    tracklets = _int("tracklets_linked_last")
    new_total = _int("new_total")
    new_dc = _int("new_dark_comet")
    new_iso = _int("new_iso")

    # No run recorded at all.
    if alerts == 0 and tracklets == 0 and new_total == 0 and not s.get("last_night"):
        return "No pipeline run recorded yet — nothing to show tonight."

    tail = f", {cadence_phrase.strip()}" if cadence_phrase and cadence_phrase.strip() else ""

    # Shape the count phrase.
    if new_total == 0:
        body = f"Quiet night: {alerts} alerts ingested, {tracklets} tracklets linked, nothing flagged for review"
    elif new_total == 1:
        if new_iso == 1:
            body = f"One ISO-shape entry flagged tonight from {alerts} alerts and {tracklets} tracklets"
        elif new_dc == 1:
            body = f"One dark-comet entry flagged tonight from {alerts} alerts and {tracklets} tracklets"
        else:
            body = f"One watch-list entry tonight from {alerts} alerts and {tracklets} tracklets"
    else:
        if new_dc and new_iso:
            kinds = f"{new_dc} dark-comet, {new_iso} ISO-shape"
            body = f"{new_total} entries flagged tonight ({kinds}) from {alerts} alerts and {tracklets} tracklets"
        elif new_dc and not new_iso:
            body = f"{new_total} dark-comet entries flagged tonight from {alerts} alerts and {tracklets} tracklets"
        elif new_iso and not new_dc:
            body = f"{new_total} ISO-shape entries flagged tonight from {alerts} alerts and {tracklets} tracklets"
        else:
            body = f"{new_total} entries flagged tonight from {alerts} alerts and {tracklets} tracklets"

    sentence = f"{body}{tail}."
    # Tighten if we somehow went long.
    if len(sentence.split()) > 30:
        # Drop the tail first, then the tracklet clause as a last resort.
        sentence = f"{body}."
        if len(sentence.split()) > 30 and "and" in body:
            body = body.split(" from ")[0] + f" from {alerts} alerts"
            sentence = f"{body}{tail}."
    return sentence


# ---- Why-flagged generation ---------------------------------------------

def generate_why_flagged(entry: dict[str, Any]) -> WhyFlagged:
    """Translate the entry's trigger into plain English — name the tension.

    Every narrative *argues a position*: first paragraph names the tension
    (what's weird + what could undercut it), second paragraph names what
    would resolve it. Short arcs (<4 nights or <7 detections) are called
    out explicitly. Mock-fit caveat, if present, attaches at the end.

    >>> w = generate_why_flagged({'category':'dark_comet','num_nights':3,
    ...     'n_obs':5,'A1':1.4e-8,'null_tests':{},'e':0.7})
    >>> 'short-arc' in w.headline.lower() or 'short arc' in ' '.join(w.summary_paragraphs).lower()
    True

    >>> w = generate_why_flagged({'category':'iso','num_nights':3,'n_obs':4,
    ...     'e':1.15,'sigma_e':0.08,'perihelion_au':1.2,'incl_deg':130,
    ...     'null_tests':{}})
    >>> isinstance(w, WhyFlagged) and len(w.summary_paragraphs) >= 1
    True
    """
    category = entry.get("category", "")
    tests = entry.get("null_tests", {}) or {}
    e = entry.get("e")
    short_arc = _is_short_arc(entry)
    mock_caveat = _mock_fit_caveat(entry)

    if category == "dark_comet":
        ok, term, mag = _has_nongrav(entry)
        ratio = _ratio_over_threshold(entry)
        n_obs = entry.get("n_obs") or 0
        n_nights = entry.get("num_nights") or 0

        systematic_state, systematic_detail = _null_test_state(tests, "instrument_systematic")
        has_systematic_warning = systematic_state == "warn"

        if has_systematic_warning:
            headline = (
                "Non-grav signature present, though the chip-correlation null test "
                "suggests an instrument systematic before a real effect."
            )
            tension = (
                f"The {term or 'A1'} term of {_fmt_sci(mag) if mag else '—'} AU/d² "
                f"is the orbital fingerprint dark comets are supposed to leave — "
                f"but the pipeline also noticed these {n_obs} detections across "
                f"{n_nights} nights concentrate on the same detector. That is the "
                "textbook look of a chip-level astrometric offset faking a radial "
                "acceleration, and on a short arc the two are not cleanly "
                "separable from the alert stream alone."
            )
            resolution = (
                "What would settle it: an extended arc that crosses multiple CCDs, "
                "or independent astrometry from a second broker. If the non-grav "
                "signature survives a chip-diverse re-fit, the systematic is "
                "ruled out; if it melts, this was never real."
            )
        elif ratio and ratio >= 5 and not short_arc:
            headline = (
                "Strong non-grav acceleration with no visible coma — the defining "
                "dark-comet signature."
            )
            tension = (
                f"The {term} term sits at {_fmt_sci(mag)} AU/d², roughly "
                f"{ratio:.0f}× the cometary-activity floor. An ordinary comet "
                "pushing this hard would show a coma or tail in the difference "
                "images; this one is point-source-consistent. That combination "
                "is exactly what Seligman et al. (2023) defined the dark-comet "
                "class to capture — a body that pushes on itself without "
                "looking like it is doing anything."
            )
            resolution = (
                "What would firm it up: the arc holding the non-grav signature "
                "past 14 nights, deep follow-up imaging still showing no coma, "
                "and thermal IR photometry consistent with a small, dark body. "
                "Any of those three failing would fold this back into the "
                "comet or artifact bin."
            )
        elif ratio and ratio >= 5 and short_arc:
            headline = (
                "Large non-grav term, but the arc is short — non-grav terms "
                "overstate themselves on short arcs."
            )
            tension = (
                f"A {term} term {ratio:.0f}× the activity floor is, on a long "
                "arc, the signature that defines a dark comet. On "
                f"{n_obs} detections over {n_nights} nights it is also exactly "
                "what a short-arc orbit fit produces when it over-reaches — "
                "the radial degree of freedom absorbs astrometric noise that a "
                "longer baseline would average out. The magnitude is "
                "suggestive; the short arc is the reason to be cautious."
            )
            resolution = (
                "What would resolve it: more nights. A 14-night arc either "
                "shrinks the non-grav amplitude back toward the floor (case "
                "closed as noise) or keeps it — at which point the dark-comet "
                "hypothesis becomes the one to beat."
            )
        elif ratio and ratio > 1:
            headline = (
                "Non-grav signature sits just above threshold — this one is a "
                "defer-and-watch, not a call."
            )
            tension = (
                f"The {term} term at {_fmt_sci(mag)} AU/d² is about "
                f"{ratio:.1f}× the pipeline's detection floor. Difference "
                "imaging is PSF-consistent, no coma. That is enough to flag, "
                "but on these numbers the argument 'real non-grav effect' and "
                "the argument 'short-arc fit wobble' look almost the same "
                "— the threshold was set where the two populations meet."
            )
            resolution = (
                "A few more nights of arc are the cheapest way to separate "
                "the two: a genuine signature firms up, a fit-artifact drifts "
                "back below threshold. This is why Defer exists."
            )
        else:
            # Morphology + short-arc fallback — the case the audit flagged.
            headline = (
                f"{n_obs} detections over {n_nights} nights is the minimum "
                "we accept — this is a short-arc call, where non-grav signals "
                "fake themselves more often than they reveal themselves."
            )
            tension = (
                "The pipeline flagged this on PSF-consistent morphology and a "
                "small non-grav term that sits around the detection floor. "
                "Neither of those is wrong, but neither is load-bearing on "
                "its own — a short arc with no visible coma is a profile "
                "shared by quiet asteroids, fit-artifact wobble, and the "
                "occasional genuine dark comet. The entry exists to be "
                "watched, not yet to be argued."
            )
            resolution = (
                "The cheapest decider is more arc: another 7–14 nights either "
                "sharpens the non-grav term into something real or lets it "
                "relax back below threshold. Until then, Defer is the honest "
                "call."
            )

        # Stitch mock-caveat to the end of the resolution paragraph if present.
        if mock_caveat:
            resolution = resolution + mock_caveat

        triggers = [
            Trigger(
                label=f"{term} non-grav term above threshold" if term else "Non-grav term above threshold",
                passed=bool(ok),
                observed=f"{_fmt_sci(mag)} AU/d²" if mag is not None else "—",
                threshold="≥ 1.0e-9 AU/d² (A1)" if term == "A1" else "≥ 1.0e-10 AU/d² (A2/A3)",
            ),
            Trigger(
                label="Morphology PSF-consistent (no coma)",
                passed=_null_test_state(tests, "image_artifact")[0] == "pass",
                observed="no coma detected",
            ),
            Trigger(
                label="No known-SSO match within tolerance",
                passed=_null_test_state(tests, "known_sso_match")[0] == "pass",
                observed=entry.get("mpc_crossmatch") or "—",
            ),
            Trigger(
                label="Bound orbit (not hyperbolic)",
                passed=(isinstance(e, (int, float)) and e is not None and e < 1.0),
                observed=f"e = {e:.3f}" if isinstance(e, (int, float)) else "—",
                threshold="e < 1.0",
            ),
        ]
        if has_systematic_warning:
            triggers.insert(
                3,
                Trigger(
                    label="Instrument systematic — unresolved",
                    passed=False,
                    observed=systematic_detail[:80] + ("…" if len(systematic_detail) > 80 else ""),
                    threshold="no chip correlation",
                ),
            )

        return WhyFlagged(
            headline=headline,
            summary_paragraphs=[tension, resolution],
            triggers=triggers,
        )

    if category == "iso":
        mpc = (entry.get("mpc_crossmatch") or "").lower()
        matches_known = "3i/atlas" in mpc or "borisov" in mpc or "oumuamua" in mpc
        e_val = e if isinstance(e, (int, float)) else None
        sigma_e = entry.get("sigma_e")
        q = entry.get("perihelion_au")
        incl = entry.get("incl_deg") or 0
        n_obs = entry.get("n_obs") or 0
        n_nights = entry.get("num_nights") or 0
        # σ(e) budget from configs/thresholds-commissioning.yaml (ISO gate).
        max_sigma_e = 0.1
        sigma_below_threshold = (
            isinstance(sigma_e, (int, float)) and sigma_e is not None and sigma_e < max_sigma_e
        )

        e_fmt = f"{e_val:.2f}" if isinstance(e_val, (int, float)) else "—"
        sigma_fmt = f"{sigma_e:.2f}" if isinstance(sigma_e, (int, float)) else "—"

        if matches_known:
            headline = (
                "Hyperbolic orbit matching a known ISO — most likely a rediscovery, "
                "not a new object."
            )
            tension = (
                f"The best-fit trajectory (e = {e_fmt}"
                f"{f' ± {sigma_fmt}' if sigma_e else ''}) lands within uncertainty "
                "of a published interstellar object. The orbital signature is "
                "genuinely hyperbolic; the open question is identity, not "
                "class. A chance coincidence at these orbital elements is "
                "unlikely but not negligible on a short arc."
            )
            resolution = (
                "Follow-up at the known ISO's predicted ephemeris settles it: "
                "if the object is there, this was a rediscovery and the "
                "pipeline did its job; if not, the coincidence was real. "
                "Under ADR-0005, it stays watch-list until that observation "
                "exists."
            )
        elif e_val is not None and e_val > 1.2 and short_arc and not sigma_below_threshold:
            headline = (
                f"Hyperbolic orbit — but the {n_nights}-night arc is right on "
                "the edge of what σ(e) can resolve."
            )
            tension = (
                f"Best-fit e = {e_fmt}{f' ± {sigma_fmt}' if sigma_e else ''} is "
                "well above the gravitational-binding threshold, which is the "
                "signature of an interstellar object. But on "
                f"{n_obs} detections over {n_nights} nights, σ(e) sits at or "
                f"above the {max_sigma_e:.2f} budget the pipeline uses to "
                "decide whether an 'unbound' fit is distinguishable from a "
                "high-e Centaur or long-period comet at all. 'Oumuamua took "
                "818 observations over 80 days to settle this same question."
            )
            resolution = (
                "The cheap test is more arc with tighter astrometry: either "
                "σ(e) shrinks below threshold while e stays > 1 (ISO "
                "hypothesis firms up) or the refit pulls e back under 1 "
                "(bound solution wins). Independent astrometry from a second "
                "broker would accelerate this."
            )
        elif e_val is not None and e_val > 1.2 and sigma_below_threshold:
            headline = (
                "Hyperbolic orbit, and σ(e) is below the refusal threshold "
                "— this one is testable."
            )
            tension = (
                f"Best-fit e = {e_fmt} ± {sigma_fmt} puts the trajectory "
                "cleanly above the gravitational-binding threshold, with an "
                "uncertainty small enough that the usual short-arc escape "
                "hatch (high-e Centaur masquerading as unbound) is genuinely "
                "closed. The orbital argument is doing real work; the "
                "remaining risk is astrometric, not kinematic."
            )
            resolution = (
                "What would confirm: independent astrometry from an external "
                "observatory at the predicted ephemeris, plus a "
                "spectroscopic or colour fingerprint. Under ADR-0005, "
                "watch-list status holds until that follow-up lands."
            )
        elif e_val is not None and e_val > 1.2:
            headline = (
                "Strongly hyperbolic best-fit — but short arcs fake non-grav "
                "and non-bound signals more often than they reveal them."
            )
            tension = (
                f"Best-fit e = {e_fmt}{f' ± {sigma_fmt}' if sigma_e else ''} "
                "is well above e = 1. That is the orbital signature of an "
                "interstellar object, and it is also a signature that pops "
                "out of short-arc fits when astrometric noise aligns the "
                "wrong way. The magnitude alone does not distinguish the two."
            )
            resolution = (
                "Extended arc with independent follow-up astrometry is the "
                "mandatory next step per ADR-0005. A tightened σ(e) with e "
                "still > 1 firms this up; a relaxed e < 1 resolves it as "
                "a high-e bound orbit."
            )
        else:
            headline = (
                "Marginal hyperbolic fit — the short arc cannot separate "
                "'unbound' from 'high-e Centaur'."
            )
            tension = (
                f"Best-fit e = {e_fmt} sits just above 1, but "
                f"{'σ(e) is large' if not sigma_e else f'σ(e) = {sigma_fmt}'} "
                "and the arc is short. A high-eccentricity bound orbit — "
                "Centaur, long-period comet, Oort returner — fits within "
                "that uncertainty just as well as an unbound solution. "
                "Alert-only data cannot decide between the two on these "
                "numbers alone."
            )
            resolution = (
                "This is exactly the case the two-stage gate was built for: "
                "wait for more arc or follow-up astrometry rather than "
                "promoting on a short-arc fit that the orbit fitter itself "
                "is warning about."
            )

        # Attach mock-fit caveat at the END of the resolution paragraph.
        if mock_caveat:
            resolution = resolution + mock_caveat

        triggers = [
            Trigger(
                label="Hyperbolic best-fit eccentricity",
                passed=(e_val is not None and e_val > 1.0),
                observed=f"e = {e_val:.3f}" if e_val is not None else "—",
                threshold="e > 1.0",
            ),
            Trigger(
                label="σ(e) below uncertainty budget",
                passed=(sigma_e is not None and sigma_e < 0.5),
                observed=f"σ(e) = {sigma_e:.2f}" if sigma_e is not None else "—",
                threshold="σ(e) < 0.5",
            ),
            Trigger(
                label="Perihelion within plausible range",
                passed=(q is not None and 0.1 <= q <= 50),
                observed=f"q = {q:.2f} AU" if q is not None else "—",
                threshold="0.1 ≤ q ≤ 50 AU",
            ),
            Trigger(
                label="Retrograde / unusual inclination" if incl > 90 else "Prograde inclination",
                passed=True,
                observed=f"i = {incl:.1f}°",
            ),
            Trigger(
                label="No known-SSO match within tolerance" if not matches_known else "MPC match (likely rediscovery)",
                passed=not matches_known,
                observed=(entry.get("mpc_crossmatch") or "—")[:80],
            ),
        ]

        return WhyFlagged(
            headline=headline,
            summary_paragraphs=[tension, resolution],
            triggers=triggers,
        )

    # Fallback
    return WhyFlagged(
        headline="Flagged by pipeline thresholds",
        summary_paragraphs=["No category-specific narrative available."],
        triggers=[],
    )


# ---- Hypothesis generation ----------------------------------------------

def generate_hypotheses(entry: dict[str, Any]) -> list[Hypothesis]:
    """Ordered list of plausible identities with what would confirm/refute each."""
    category = entry.get("category", "")
    tests = entry.get("null_tests", {}) or {}
    ratio = _ratio_over_threshold(entry)
    systematic_state, _ = _null_test_state(tests, "instrument_systematic")
    has_systematic = systematic_state == "warn"
    e = entry.get("e")

    if category == "dark_comet":
        out: list[Hypothesis] = []

        leading_likelihood = "leading" if (ratio and ratio >= 5 and not has_systematic) else "plausible"
        out.append(Hypothesis(
            name="Dark comet",
            tagline="A body with non-grav acceleration but no visible outgassing",
            likelihood=leading_likelihood,
            description=(
                "A recently-defined class of Solar System body (Seligman et al. 2023, ApJ 162:229). "
                "Shows the orbital signature of outgassing without any imaging evidence of a coma "
                "or tail. About seven are known; Rubin is expected to find many. Physical models "
                "under investigation include H₂-dominated outgassing, subsurface ice sublimating "
                "below detection limits, and radiation-pressure effects on low-density bodies."
            ),
            supports=[
                f"A1/A2/A3 non-grav term {f'{ratio:.1f}× threshold' if ratio else 'present'}",
                "Difference-image morphology PSF-consistent (no coma)",
                "Bound orbit rules out interstellar origin",
            ],
            would_confirm=[
                "Extended arc (≥ 14 nights) holds the non-grav signature",
                "Deep follow-up imaging shows no CO₂/H₂O emission",
                "Thermal IR photometry consistent with small, dark body",
            ],
            would_refute=[
                "Subsequent imaging reveals a faint coma",
                "Non-grav signature fades with longer arc (= transient outburst)",
            ],
        ))

        out.append(Hypothesis(
            name="Low-activity Jupiter-family comet",
            tagline="A comet quiet enough that its coma is below Rubin's per-visit detection floor",
            likelihood="plausible",
            description=(
                "An otherwise ordinary cometary body whose outgassing is weak enough — at this "
                "heliocentric distance, at this phase of activity — that Rubin's difference imaging "
                "doesn't detect the coma even though the orbital non-grav signature is real."
            ),
            supports=[
                "Non-grav term magnitude is consistent with typical comet-activity ranges",
                "Bound orbit is typical of the JFC family",
            ],
            would_confirm=[
                "Deeper co-added imaging reveals faint coma",
                "Color photometry in r/i consistent with dusty comet (not asteroid-like)",
                "Activity ramps up at smaller heliocentric distance",
            ],
            would_refute=[
                "Follow-up spectroscopy shows no volatile emission lines",
            ],
        ))

        out.append(Hypothesis(
            name="Unusual near-Earth asteroid with thermal perturbation",
            tagline="Yarkovsky/YORP reaching detectable magnitudes on a small rocky body",
            likelihood="unlikely",
            description=(
                "Non-gravitational forces on asteroids come from anisotropic thermal re-radiation "
                "(Yarkovsky effect) or spin-driven torques (YORP). These are usually orders of "
                "magnitude smaller than cometary outgassing forces but can creep into the detectable "
                "range on very small, fast-rotating bodies with high obliquity."
            ),
            supports=[
                "Consistent with a small dark body if the non-grav amplitude is at the low end",
            ],
            would_confirm=[
                "Rotational light curve consistent with a small tumbling object",
                "Spectrum consistent with a carbonaceous or metallic composition",
            ],
            would_refute=[
                "Non-grav magnitude exceeds what Yarkovsky can plausibly produce",
                "Detected activity (coma/tail) in follow-up",
            ],
        ))

        if has_systematic:
            out.insert(0, Hypothesis(
                name="Instrument systematic",
                tagline="A chip-level correlation producing phantom non-grav acceleration",
                likelihood="systematic",
                description=(
                    "The suspicious-detector null test flagged that most of this object's detections "
                    "land on the same CCD. Systematic astrometric offsets on a single chip can mimic "
                    "a tiny radial acceleration — especially on short arcs. Before accepting any of "
                    "the other hypotheses, this has to be ruled out."
                ),
                supports=[
                    "Detection chip distribution is highly non-uniform",
                    "Short arc means few independent astrometric anchors",
                ],
                would_confirm=[
                    "Same pattern recurs on unrelated objects observed on the same chip",
                    "Signature vanishes in an arc that visits multiple chips",
                ],
                would_refute=[
                    "Object re-detected on a different chip at consistent astrometry",
                    "Independent broker's pipeline confirms the non-grav signature",
                ],
            ))

        return out

    if category == "iso":
        mpc = (entry.get("mpc_crossmatch") or "").lower()
        matches_known = "3i/atlas" in mpc or "borisov" in mpc or "oumuamua" in mpc

        out: list[Hypothesis] = []

        if matches_known:
            out.append(Hypothesis(
                name="Rediscovery of a known ISO",
                tagline="Orbital parameters fall within uncertainty of a published interstellar object",
                likelihood="leading",
                description=(
                    "The MPC cross-match flagged this tracklet's orbit as consistent with a known "
                    "ISO (likely 3I/ATLAS, per the cross-match note). This is a validation case — "
                    "the pipeline correctly identified a known object. It stays on the watch list "
                    "until independent astrometry confirms the association rather than a chance "
                    "orbital coincidence."
                ),
                supports=[
                    "Orbital elements match the known ISO within σ",
                    "Retrograde inclination / large eccentricity signature",
                ],
                would_confirm=[
                    "Follow-up observation at the predicted ephemeris of the known ISO",
                    "Colors / light curve consistent with the published object",
                ],
                would_refute=[
                    "Refit with extended arc drifts away from the known orbit",
                ],
            ))

        out.append(Hypothesis(
            name="New interstellar object",
            tagline="Unbound trajectory with no prior astrometry — a novel detection",
            likelihood="plausible" if not matches_known else "unlikely",
            description=(
                "Rubin is expected to discover 1–10 genuine interstellar objects per year (Hoover "
                "et al. 2022, Marceta & Seligman 2023). Confirming one from alert-only data is "
                "extremely difficult — 'Oumuamua required 818 observations over 80 days before "
                "its hyperbolic nature was robustly established (Micheli et al. 2018)."
            ),
            supports=[
                "Best-fit e > 1 with σ(e) inside the watch-list budget",
                "Perihelion within the plausible ISO discovery range",
            ],
            would_confirm=[
                "Independent astrometry from an external observatory",
                "Extended arc that keeps e > 1 with smaller σ(e)",
                "Spectroscopic fingerprint (gas, dust, or 'Oumuamua-like inertness)",
            ],
            would_refute=[
                "Refit on extended arc yields e clearly < 1 (high-e Centaur / Oort returner)",
            ],
        ))

        out.append(Hypothesis(
            name="High-eccentricity bound object",
            tagline="Centaur or long-period comet masquerading as unbound on a short arc",
            likelihood="plausible",
            description=(
                "Short-arc orbit fits struggle to separate truly unbound (e > 1) trajectories from "
                "high-e bound orbits. A Centaur or incoming long-period comet with e = 0.98 can fit "
                "a 3-night tracklet with a best-fit e > 1 well within σ. This is the hypothesis "
                "that's hardest to rule out from the alert stream alone."
            ),
            supports=[
                "Short arc leaves room for a bound solution within σ(e)",
                "Perihelion and inclination are also consistent with outer-SS bodies",
            ],
            would_confirm=[
                "Extended arc pulls the orbit solution below e = 1",
            ],
            would_refute=[
                "Extended arc keeps e > 1 with shrinking σ(e)",
            ],
        ))

        out.append(Hypothesis(
            name="Short-arc artifact",
            tagline="Orbit-fit instability on 3 nights of 4 detections",
            likelihood="unlikely",
            description=(
                "Pathological short-arc fits can return spurious hyperbolic orbits when the "
                "tracklet-linking step is mildly wrong, or when a single astrometric outlier "
                "pulls the fit. The null-hypothesis checklist is designed to catch this, but "
                "short-arc artifacts are the default skepticism."
            ),
            supports=[],
            would_confirm=[
                "Refit without the suspect detection yields a normal bound orbit",
                "The tracklet linker gets challenged by injected fake alerts and fails similarly",
            ],
            would_refute=[
                "All null-hypothesis tests already pass cleanly",
                "Orbit fit is well-constrained (σ(e) much smaller than 1.0)",
            ],
        ))

        return out

    return []


# ---- Lightweight glossary for orbital elements --------------------------

ORBITAL_ELEMENT_GLOSSARY: dict[str, str] = {
    "a": "semi-major axis — the orbit's overall size",
    "e": "eccentricity — 0 is a circle, <1 is bound, >1 is unbound",
    "i": "inclination — tilt of the orbit relative to the planets",
    "q": "perihelion — closest approach to the Sun",
    "Q": "aphelion — farthest distance from the Sun (bound orbits only)",
    "A1": "radial non-gravitational acceleration (toward/away from the Sun)",
    "A2": "transverse non-grav acceleration (along the orbit)",
    "A3": "normal non-grav acceleration (out of the orbital plane)",
    "rms": "astrometric fit residual — lower is a better orbit fit",
}
