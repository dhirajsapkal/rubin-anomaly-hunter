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


# ---- Why-flagged generation ---------------------------------------------

def generate_why_flagged(entry: dict[str, Any]) -> WhyFlagged:
    """Translate the entry's trigger into plain English."""
    category = entry.get("category", "")
    tests = entry.get("null_tests", {}) or {}
    e = entry.get("e")

    if category == "dark_comet":
        ok, term, mag = _has_nongrav(entry)
        ratio = _ratio_over_threshold(entry)
        n_obs = entry.get("n_obs") or 0
        n_nights = entry.get("num_nights") or 0

        systematic_state, systematic_detail = _null_test_state(tests, "instrument_systematic")
        has_systematic_warning = systematic_state == "warn"

        if has_systematic_warning:
            headline = "Non-grav signature — but a systematic is suspected"
            intro = (
                f"Over {n_obs} detections across {n_nights} nights, this object's orbital fit required "
                f"a {term} non-gravitational term to close — the hallmark of a dark-comet candidate. "
                "However, the pipeline also noticed that an unusually large fraction of those detections "
                "land on the same detector, which is a classic signature of an instrument systematic "
                "masquerading as a real effect."
            )
            followup = (
                "Before anything else, this needs a hard look at whether the object is really moving "
                "or whether one detector chip is producing correlated residuals. An extended arc that "
                "visits different chips would resolve this quickly."
            )
        elif ratio and ratio >= 5:
            headline = "Strong non-gravitational acceleration, no visible coma"
            intro = (
                f"Over {n_obs} detections across {n_nights} nights, this object's orbit requires a "
                f"radial {term} term of {_fmt_sci(mag)} AU/d² — about {ratio:.0f}× the pipeline's "
                "cometary-activity floor. In ordinary comets, an acceleration of this magnitude shows up "
                "as visible outgassing — a coma or tail in the difference images."
            )
            followup = (
                "These difference images are point-source-consistent. The combination is exactly what "
                "defines the dark-comet class (Seligman et al. 2023): a body that pushes on itself "
                "without looking like it's doing anything."
            )
        elif ratio and ratio > 1:
            headline = "Non-grav signature sits just above threshold"
            intro = (
                f"This entry's {term} term of {_fmt_sci(mag)} AU/d² sits about {ratio:.1f}× the "
                "pipeline's detection floor — enough to flag, but not by a lot. The difference-image "
                "cutouts show no visible coma or tail."
            )
            followup = (
                "This is a good candidate for Defer: a few more nights of arc will either firm up the "
                "non-grav signature or let it fall back below threshold."
            )
        else:
            headline = "Flagged on morphology + short-arc signal"
            intro = (
                f"{n_obs} detections across {n_nights} nights, difference-image morphology "
                "PSF-consistent, no known-SSO match. The non-grav terms from the orbit fit are "
                "small but present."
            )
            followup = (
                "The case is not yet strong. More arc is the usual resolution."
            )

        triggers = [
            Trigger(
                label=f"{term} non-grav term above threshold",
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
            summary_paragraphs=[intro, followup],
            triggers=triggers,
        )

    if category == "iso":
        mpc = (entry.get("mpc_crossmatch") or "").lower()
        matches_known = "3i/atlas" in mpc or "borisov" in mpc or "oumuamua" in mpc
        e_val = e if isinstance(e, (int, float)) else None
        sigma_e = entry.get("sigma_e")
        q = entry.get("perihelion_au")
        incl = entry.get("incl_deg") or 0

        if matches_known:
            headline = "Hyperbolic orbit matching a known ISO"
            intro = (
                f"The pipeline fit a best-fit hyperbolic trajectory (e = {e_val:.2f}"
                f"{f' ± {sigma_e:.2f}' if sigma_e else ''}) to this tracklet. The orbital parameters "
                "— eccentricity, perihelion, retrograde inclination — fall within uncertainty of a "
                "known interstellar object."
            )
            followup = (
                "This is most likely a rediscovery, not a new ISO. Under ADR-0005, it still sits on "
                "the watch list until independent follow-up astrometry confirms the match."
            )
        elif e_val is not None and e_val > 1.2:
            headline = "Strongly hyperbolic orbit — ISO candidate"
            intro = (
                f"Best-fit eccentricity e = {e_val:.2f}"
                f"{f' ± {sigma_e:.2f}' if sigma_e else ''} is well above the gravitational-binding "
                "threshold (e = 1). The pipeline cannot close this orbit on any bound trajectory."
            )
            followup = (
                "Before calling this a real ISO detection, an extended arc with follow-up astrometry "
                "is mandatory. A 3-night tracklet can fake e > 1 more often than people expect."
            )
        else:
            headline = "Marginal hyperbolic fit — more arc needed"
            intro = (
                f"Best-fit e = {e_val:.2f if e_val else '—'} sits just above 1, but σ(e) is large "
                "enough that a high-eccentricity bound orbit (Centaur, long-period comet) isn't ruled "
                "out."
            )
            followup = (
                "This is why the pipeline uses a two-stage gate: alert-only short-arc data cannot "
                "distinguish 'unbound' from 'high-e Centaur' without more observations."
            )

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
            summary_paragraphs=[intro, followup],
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
