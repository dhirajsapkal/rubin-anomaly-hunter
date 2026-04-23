"""Null-hypothesis tests for watch-list entries (PRD §10).

Seven mandatory checks; failures reject a watch-list entry (or flag it
for review). At M0 most of these are stubs so the dashboard and audit
log can display them with the right shape; the real logic arrives later.

Each test returns a ``NullTestResult``:
    passed   — True when the null hypothesis is rejected (i.e. the
               object survives the check)
    detail   — short human-readable explanation
    severity — "info" | "warn" | "reject" (for UI sorting / colour)

The dictionary returned by ``run_null_tests`` is keyed by the PRD §10
test name so the dashboard can render them in a fixed order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class NullTestResult:
    passed: bool
    detail: str
    severity: str  # "info", "warn", "reject"
    name: str = ""


TEST_NAMES = [
    "mpc_cross_match",
    "cometary_outgassing_normal",
    "image_artifact",
    "streak_residual",
    "short_arc_ambiguity",
    "instrument_systematic",
    "broker_flag_drift",
]


def run_null_tests(
    tracklet: Any,
    orbit_fit: Any,
    morphology: dict,
) -> dict[str, NullTestResult]:
    """Run all seven null-hypothesis tests and return a keyed dict.

    Parameters are kept as ``Any`` to avoid a circular import dependency
    with the linker / fitter; each individual test pulls attributes
    defensively.
    """
    return {
        "mpc_cross_match": _mpc_cross_match(tracklet, orbit_fit),
        "cometary_outgassing_normal": _cometary_outgassing(orbit_fit, morphology),
        "image_artifact": _image_artifact(morphology),
        "streak_residual": _streak_residual(tracklet, morphology),
        "short_arc_ambiguity": _short_arc_ambiguity(tracklet),
        "instrument_systematic": _instrument_systematic(tracklet),
        "broker_flag_drift": _broker_flag_drift(tracklet),
    }


# ---------------------------------------------------------------------------
# Individual tests
# ---------------------------------------------------------------------------


def _mpc_cross_match(tracklet: Any, orbit_fit: Any) -> NullTestResult:
    """PRD §10.1: known Solar System object cross-match. Stub at M0;
    production version will hit MPC Explorer or `sbpy.data.Names` with
    a per-object-class tolerance."""
    return NullTestResult(
        passed=True,
        detail="stub — M0; no MPC lookup performed",
        severity="info",
        name="mpc_cross_match",
    )


def _cometary_outgassing(orbit_fit: Any, morphology: dict) -> NullTestResult:
    """PRD §10.2: reject from DARK-COMET watch-list if non-grav
    magnitudes are consistent with a normal comet AND morphology shows
    any coma. At M0 we only run the morphology half — treating A1/A2/A3
    consistency checks as future work because we need a population to
    compare against."""
    coma = bool(morphology.get("coma_flag", False))
    extendedness = float(morphology.get("extendedness", 0.0))
    if coma or extendedness > 0.5:
        return NullTestResult(
            passed=False,
            detail=(
                f"morphology indicates coma (coma_flag={coma}, "
                f"extendedness={extendedness:.2f}); route to cometary list"
            ),
            severity="reject",
            name="cometary_outgassing_normal",
        )
    return NullTestResult(
        passed=True,
        detail="morphology PSF-consistent; full A1/A2/A3 normality check pending",
        severity="info",
        name="cometary_outgassing_normal",
    )


def _image_artifact(morphology: dict) -> NullTestResult:
    """PRD §10.3: reliability score below R_min, or difference-image
    ringing / negative-companion artifacts. Uses whatever the broker
    reported; stub otherwise."""
    rb = morphology.get("reliability")
    if rb is None:
        return NullTestResult(
            passed=True,
            detail="no reliability score provided; stub pass",
            severity="info",
            name="image_artifact",
        )
    if rb < 0.5:
        return NullTestResult(
            passed=False,
            detail=f"reliability={rb:.2f} below 0.5 — likely artifact",
            severity="reject",
            name="image_artifact",
        )
    return NullTestResult(
        passed=True,
        detail=f"reliability={rb:.2f}",
        severity="info",
        name="image_artifact",
    )


def _streak_residual(tracklet: Any, morphology: dict) -> NullTestResult:
    """PRD §10.4: Starlink / satellite streak residual or streak-endpoint
    adjacency. Stub at M0 — the streak-flag column is expected on the
    detections table once the data-layer agent wires it up."""
    streak = bool(morphology.get("streak_flag", False))
    if streak:
        return NullTestResult(
            passed=False,
            detail="streak_flag set — likely satellite streak residual",
            severity="reject",
            name="streak_residual",
        )
    return NullTestResult(
        passed=True,
        detail="no streak flag reported",
        severity="info",
        name="streak_residual",
    )


def _short_arc_ambiguity(tracklet: Any) -> NullTestResult:
    """PRD §10.5: requeue rather than promote if the arc is too short or
    the tracklet quality flag indicates linking uncertainty."""
    n_nights = int(getattr(tracklet, "n_nights", 0) or 0)
    n_det = int(getattr(tracklet, "n_detections", 0) or 0)
    quality = str(getattr(tracklet, "quality_flag", "ok") or "ok")

    if quality in {"suspect", "mock"}:
        severity = "warn" if quality == "mock" else "reject"
        return NullTestResult(
            passed=False,
            detail=f"tracklet quality flag '{quality}' — requeue, do not promote",
            severity=severity,
            name="short_arc_ambiguity",
        )
    if n_nights < 2 or n_det < 3:
        return NullTestResult(
            passed=False,
            detail=f"short arc: {n_det} det over {n_nights} nights",
            severity="warn",
            name="short_arc_ambiguity",
        )
    return NullTestResult(
        passed=True,
        detail=f"{n_det} det over {n_nights} nights",
        severity="info",
        name="short_arc_ambiguity",
    )


def _instrument_systematic(tracklet: Any) -> NullTestResult:
    """PRD §10.6: correlation with a specific CCD / filter / airmass /
    moon-phase bin. Stub at M0; needs a per-night distribution cache."""
    return NullTestResult(
        passed=True,
        detail="stub — M0; per-night systematic correlation not yet computed",
        severity="info",
        name="instrument_systematic",
    )


def _broker_flag_drift(tracklet: Any) -> NullTestResult:
    """PRD §10.7: re-query broker context at review time and compare
    against the ingest-time snapshot. Stub at M0 — the ingest layer
    must expose the snapshot first (ADR-0009)."""
    return NullTestResult(
        passed=True,
        detail="stub — M0; broker flag comparison pending ingest snapshot API",
        severity="info",
        name="broker_flag_drift",
    )
