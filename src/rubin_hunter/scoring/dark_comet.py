"""Dark-comet watch-list scoring.

Applies the dark-comet gates from ADR-0004 / ADR-0005 / ADR-0006 and the
frozen thresholds in `rubin_hunter.config.DarkCometThresholds`. The output
is an explicit pass/fail with per-gate reasons so the review UI can show
"why did or didn't this promote?" to the operator.

Confidence scoring tries, in order:
    1. coniferest.IsolationForest (if installed — preferred per PRD §6)
    2. scikit-learn IsolationForest fallback
    3. Z-score on A1 magnitude across the population

At M0 the training corpus is empty; the forest scorers fall back on a
single-point fit of a trivial reference distribution so they produce
something the dashboard can display. That is labelled in the output.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from rubin_hunter.config import DarkCometThresholds
from rubin_hunter.orbit.find_orb_wrapper import OrbitFit

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------


@dataclass
class DarkCometScore:
    passes: bool
    reasons: list[str]
    confidence: float
    gates: dict[str, bool] = field(default_factory=dict)
    scorer_used: str = "zscore"

    def as_row(self) -> dict[str, Any]:
        return {
            "passes": self.passes,
            "confidence": self.confidence,
            "reasons": "; ".join(self.reasons),
            "gates": self.gates,
            "scorer_used": self.scorer_used,
        }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def score_dark_comet(
    orbit_fit: OrbitFit,
    morphology: dict,
    thresholds: DarkCometThresholds,
    *,
    population: np.ndarray | None = None,
) -> DarkCometScore:
    """Evaluate a single tracklet against the dark-comet watch-list gates.

    Parameters
    ----------
    orbit_fit
        `OrbitFit` from find_orb / mock.
    morphology
        dict with at least the key ``extendedness`` (float, stellar PSF
        baseline 0.0; comae push it toward 1.0). Optional keys:
        ``coma_flag`` (bool), ``tail_flag`` (bool), ``psf_chi2`` (float).
    thresholds
        DarkCometThresholds from the frozen config.
    population
        Optional array of |A1| values from prior fits. If provided, the
        confidence z-score is computed against this distribution instead
        of a synthetic prior.
    """
    reasons: list[str] = []
    gates: dict[str, bool] = {}

    # ---- Gate: non-grav magnitudes ---------------------------------------
    a1_ok = abs(orbit_fit.A1) >= thresholds.A1_min_au_per_day2
    a2_ok = abs(orbit_fit.A2) >= thresholds.A2_min_au_per_day2
    a3_ok = abs(orbit_fit.A3) >= thresholds.A3_min_au_per_day2
    nongrav_any = a1_ok or a2_ok or a3_ok
    gates["nongrav_above_min"] = nongrav_any
    if nongrav_any:
        reasons.append(
            f"non-grav above threshold (|A1|={abs(orbit_fit.A1):.2e}, "
            f"|A2|={abs(orbit_fit.A2):.2e}, |A3|={abs(orbit_fit.A3):.2e})"
        )
    else:
        reasons.append("non-grav magnitudes below all thresholds")

    # ---- Gate: measurement, not noise (relative sigma) -------------------
    def rel_sigma(val: float, sig: float) -> float:
        return sig / abs(val) if abs(val) > 0 else math.inf

    rel_sigmas = {
        "A1": rel_sigma(orbit_fit.A1, orbit_fit.sigma_A1),
        "A2": rel_sigma(orbit_fit.A2, orbit_fit.sigma_A2),
        "A3": rel_sigma(orbit_fit.A3, orbit_fit.sigma_A3),
    }
    # Only evaluate rel-sigma on components that passed the magnitude gate;
    # zero-magnitude components have undefined relative sigma.
    relevant = []
    if a1_ok:
        relevant.append(("A1", rel_sigmas["A1"]))
    if a2_ok:
        relevant.append(("A2", rel_sigmas["A2"]))
    if a3_ok:
        relevant.append(("A3", rel_sigmas["A3"]))
    if relevant:
        worst = max(relevant, key=lambda kv: kv[1])
        rel_ok = worst[1] <= thresholds.max_relative_sigma
        gates["measurement_not_noise"] = rel_ok
        reasons.append(
            f"worst relative sigma on {worst[0]}: {worst[1]:.2f} "
            f"(limit {thresholds.max_relative_sigma})"
        )
    else:
        gates["measurement_not_noise"] = False
        reasons.append("no non-grav component above threshold to evaluate sigma on")

    # ---- Gate: morphology — PSF-consistent, no visible coma --------------
    extendedness = float(morphology.get("extendedness", 0.0))
    coma_flag = bool(morphology.get("coma_flag", False))
    tail_flag = bool(morphology.get("tail_flag", False))
    morph_ok = (
        extendedness <= thresholds.max_extendedness
        and not coma_flag
        and not tail_flag
    )
    gates["morphology_psf_consistent"] = morph_ok
    reasons.append(
        f"extendedness={extendedness:.2f} "
        f"(max {thresholds.max_extendedness}), coma={coma_flag}, tail={tail_flag}"
    )

    # ---- Gate: orbit must be bound ---------------------------------------
    e_plus = orbit_fit.e + orbit_fit.sigma_e
    bound_ok = e_plus < thresholds.max_eccentricity_upper
    gates["orbit_bound"] = bound_ok
    reasons.append(
        f"e+sigma(e)={e_plus:.3f} (must be < {thresholds.max_eccentricity_upper})"
    )

    # ---- Aggregate -------------------------------------------------------
    passes = all(gates.values())

    # ---- Confidence ------------------------------------------------------
    confidence, scorer_used = _confidence(orbit_fit, morphology, population)

    return DarkCometScore(
        passes=passes,
        reasons=reasons,
        confidence=confidence,
        gates=gates,
        scorer_used=scorer_used,
    )


# ---------------------------------------------------------------------------
# Confidence helpers
# ---------------------------------------------------------------------------


def _confidence(
    orbit_fit: OrbitFit,
    morphology: dict,
    population: np.ndarray | None,
) -> tuple[float, str]:
    """Return (confidence in [0, 1], scorer label).

    Uses coniferest if present, else sklearn IsolationForest, else a
    z-score on |A1|.
    """
    features = np.array(
        [
            abs(orbit_fit.A1),
            abs(orbit_fit.A2),
            abs(orbit_fit.A3),
            orbit_fit.e,
            orbit_fit.fit_rms,
            float(morphology.get("extendedness", 0.0)),
        ]
    ).reshape(1, -1)

    # --- coniferest ---
    try:
        from coniferest.isoforest import IsolationForest as ConiferForest  # type: ignore

        forest = ConiferForest(n_trees=64, random_seed=20260422)
        # Fit on a synthetic "typical asteroid" null population plus the
        # current point so it can compute a score.
        null = _synthetic_null_population()
        forest.fit(np.vstack([null, features]))
        score = forest.score_samples(features)[0]
        return _normalize_forest_score(score), "coniferest"
    except Exception:
        pass

    # --- sklearn fallback ---
    try:
        from sklearn.ensemble import IsolationForest

        forest = IsolationForest(
            n_estimators=64, contamination="auto", random_state=20260422
        )
        null = _synthetic_null_population()
        forest.fit(np.vstack([null, features]))
        score = forest.score_samples(features)[0]
        return _normalize_forest_score(score), "sklearn_isoforest"
    except Exception as exc:
        logger.debug("sklearn IsolationForest unavailable (%s); falling back", exc)

    # --- z-score fallback ---
    pop = population if population is not None and len(population) > 5 else _synthetic_A1_null()
    mu = float(np.mean(pop))
    sd = float(np.std(pop)) or 1e-12
    z = abs(abs(orbit_fit.A1) - mu) / sd
    conf = 1.0 - math.exp(-z / 3.0)
    return max(0.0, min(1.0, conf)), "zscore"


def _normalize_forest_score(score: float) -> float:
    """IsolationForest scores are roughly in [-0.5, 0.5]; the further
    negative, the more anomalous. Map to a confidence in [0, 1] where
    higher = more anomalous."""
    # sklearn convention: lower score = more anomalous.
    conf = 0.5 - score  # shift so anomalous ~ 1
    return max(0.0, min(1.0, conf))


def _synthetic_null_population(n: int = 200, seed: int = 20260422) -> np.ndarray:
    """Placeholder "typical asteroid" feature distribution. Replaced by a
    real training set after commissioning."""
    rng = np.random.default_rng(seed)
    return np.column_stack(
        [
            np.abs(rng.normal(0, 1e-10, n)),
            np.abs(rng.normal(0, 1e-11, n)),
            np.abs(rng.normal(0, 1e-11, n)),
            rng.uniform(0, 0.6, n),
            rng.uniform(0.1, 0.5, n),
            rng.uniform(0, 0.15, n),
        ]
    )


def _synthetic_A1_null(n: int = 200, seed: int = 20260422) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.abs(rng.normal(0, 1e-10, n))
