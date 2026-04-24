"""Translate quantitative fit values into hobbyist-readable phrases.

Used by the Tonight canvas and the reporting-guidance band (ADR-0018).
Every phrase is deliberately hedged: a watch-list entry is never described
as a "discovery" or "candidate" per ADR-0005, reaffirmed in ADR-0018.
The vocabulary stays in the domain of "looks like", "might be",
"confidence" — not certainty.
"""

from __future__ import annotations

from typing import Any

from .narrative import _has_nongrav


__all__ = [
    "confidence_phrase",
    "confidence_note",
    "what_we_saw",
    "hero_sentence",
    "category_label",
    "first_connected_phrase",
]


def confidence_phrase(sigma_e: float | None) -> str:
    """Map σ(e) to a two-word phrase.

    <0.05       → "confidence: high"
    0.05–0.15   → "confidence: medium"
    >0.15       → "confidence: low"
    None        → "confidence: unknown"
    """
    try:
        s = float(sigma_e) if sigma_e is not None else None
    except (TypeError, ValueError):
        s = None
    if s is None:
        return "confidence: unknown"
    if s < 0.05:
        return "confidence: high"
    if s <= 0.15:
        return "confidence: medium"
    return "confidence: low"


def confidence_note(sigma_e: float | None) -> str:
    """Longer plain-English gloss. Optional tooltip body."""
    try:
        s = float(sigma_e) if sigma_e is not None else None
    except (TypeError, ValueError):
        s = None
    if s is None:
        return ""
    if s < 0.05:
        return "Orbit fit is tight — little wiggle room."
    if s <= 0.15:
        return "Orbit fit has some wiggle — a second observation would tighten it."
    return "Orbit fit is noisy — this might just be short-arc uncertainty."


def what_we_saw(entry: dict[str, Any]) -> str:
    """Plain-English description of the anomaly.

    Leads with the physical picture ("a rock that's being pushed"), not
    the equation (A1 = 1.4e-8 AU/d²). Used in the "What we saw" canvas
    band per ADR-0018 Panel 2.
    """
    category = (entry.get("category") or "").lower()
    n_obs = int(entry.get("n_obs") or 0)

    if category == "iso":
        e = entry.get("e")
        try:
            e_val = float(e) if e is not None else None
        except (TypeError, ValueError):
            e_val = None
        if e_val is not None and e_val > 1.0:
            return (
                "This object is on an orbit that didn't come from our Solar "
                "System. Its eccentricity exceeds 1 — meaning it's unbound, "
                "falling through on a trajectory that traces back to "
                "interstellar space."
            )
        return (
            "The orbit fit suggests an unbound trajectory — but short arcs "
            "make that reading uncertain. Treat as provisional."
        )

    ok, _term, _mag = _has_nongrav(entry)
    if ok:
        n_phrase = f"{n_obs}" if n_obs else "several"
        return (
            f"This object looks like a rock — a single point of light, no "
            f"tail, no coma, no fuzzy halo in any of the {n_phrase} images. "
            f"But as it moves across the sky, its orbit doesn't quite match "
            f"gravity alone. Something is pushing it."
        )

    # Catch-all — the entry was flagged for a reason the pipeline saw.
    return (
        "This tracklet was flagged by the pipeline for closer review. "
        "The evidence below shows why — typically an unusual orbit fit, "
        "a confidence concern, or a short-arc tripwire."
    )


def hero_sentence(entry: dict[str, Any]) -> str:
    """One-liner for the canvas hero above the stat strip."""
    category = (entry.get("category") or "").lower()
    if category == "iso":
        return "An orbit that came from outside the Solar System."
    ok, _term, _ = _has_nongrav(entry)
    if ok:
        return "A rock that's being pushed by something invisible."
    return "Something unusual in tonight's feed."


def category_label(entry: dict[str, Any]) -> str:
    """Plain-language category chip text."""
    if (entry.get("category") or "").lower() == "iso":
        return "Interstellar shape"
    return "Possible dark comet"


def first_connected_phrase(entry: dict[str, Any]) -> str:
    """'you spotted this first' / 'first connected X days ago'."""
    first = (entry.get("created_utc") or "")[:10]
    if not first:
        return "first connected: unknown"
    return f"first connected {first}"
