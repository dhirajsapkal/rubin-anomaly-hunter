"""Interstellar-object (ISO) watch-list scoring.

Implements the ISO gate from ADR-0005: a hyperbolic best-fit e > 1 is only
promotable to the watch-list if the eccentricity uncertainty is small
enough that "unbound" is distinguishable from "high-eccentricity bound".
Per the PRD / ADR-0005, we STRICTLY refuse to promote when sigma_e is
above the frozen limit — Micheli et al.'s 'Oumuamua result needed 818
observations to close; a typical 3-night Rubin arc will not reach that.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from rubin_hunter.config import ISOThresholds
from rubin_hunter.orbit.find_orb_wrapper import OrbitFit

logger = logging.getLogger(__name__)


@dataclass
class ISOScore:
    passes: bool
    reasons: list[str]
    confidence: float
    gates: dict[str, bool] = field(default_factory=dict)
    refused: bool = False  # True if sigma_e refused promotion per ADR-0005
    scorer_used: str = "zscore"

    def as_row(self) -> dict[str, Any]:
        return {
            "passes": self.passes,
            "confidence": self.confidence,
            "reasons": "; ".join(self.reasons),
            "gates": self.gates,
            "refused_sigma_e": self.refused,
            "scorer_used": self.scorer_used,
        }


def score_iso(orbit_fit: OrbitFit, thresholds: ISOThresholds) -> ISOScore:
    """Evaluate a tracklet against the ISO watch-list gates (ADR-0005).

    Returns a refusal (``refused=True``, ``passes=False``) when
    ``sigma_e > thresholds.max_sigma_e`` regardless of any other gate.
    """
    reasons: list[str] = []
    gates: dict[str, bool] = {}

    # ---- Hard refusal per ADR-0005: sigma_e too large --------------------
    refused = orbit_fit.sigma_e > thresholds.max_sigma_e
    gates["sigma_e_acceptable"] = not refused
    if refused:
        reasons.append(
            f"REFUSED per ADR-0005: sigma(e)={orbit_fit.sigma_e:.3f} "
            f"exceeds max {thresholds.max_sigma_e}. "
            "Short arc cannot distinguish unbound from high-eccentricity bound."
        )
        # Still compute the rest so the dashboard can show why, but passes=False.

    # ---- Gate: e > 1 (best-fit hyperbolic) -------------------------------
    hyperbolic = orbit_fit.e > thresholds.min_best_fit_e
    gates["hyperbolic"] = hyperbolic
    reasons.append(
        f"best-fit e={orbit_fit.e:.3f} (must exceed {thresholds.min_best_fit_e})"
    )

    # ---- Gate: perihelion in plausible band ------------------------------
    q_ok = thresholds.min_perihelion_au <= orbit_fit.q <= thresholds.max_perihelion_au
    gates["perihelion_in_range"] = q_ok
    reasons.append(
        f"q={orbit_fit.q:.3f} AU (allowed "
        f"{thresholds.min_perihelion_au}..{thresholds.max_perihelion_au})"
    )

    passes = all(gates.values()) and not refused

    confidence, scorer_used = _confidence(orbit_fit)
    return ISOScore(
        passes=passes,
        reasons=reasons,
        confidence=confidence,
        gates=gates,
        refused=refused,
        scorer_used=scorer_used,
    )


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


def _confidence(orbit_fit: OrbitFit) -> tuple[float, str]:
    """Confidence of "this really is unbound".

    Normalized distance of e above 1.0 in units of sigma_e, squashed to
    [0, 1] via a logistic. Non-finite or missing sigma_e yields 0.
    """
    sigma_e = orbit_fit.sigma_e
    if sigma_e is None or not math.isfinite(sigma_e) or sigma_e <= 0:
        return 0.0, "na"
    z = (orbit_fit.e - 1.0) / sigma_e
    conf = 1.0 / (1.0 + math.exp(-z))
    return max(0.0, min(1.0, float(conf))), "zscore_on_e"


# ---------------------------------------------------------------------------
# Optional coniferest-backed secondary score, used by the dashboard only.
# ---------------------------------------------------------------------------


def anomaly_forest_score(features: np.ndarray) -> tuple[float, str]:
    """Feature-vector isolation-forest score; used for dashboard display,
    not for gate decisions."""
    try:
        from coniferest.isoforest import IsolationForest as ConiferForest  # type: ignore

        forest = ConiferForest(n_trees=64, random_seed=20260422)
        forest.fit(features.reshape(-1, features.shape[-1]))
        return float(forest.score_samples(features)[0]), "coniferest"
    except Exception:
        try:
            from sklearn.ensemble import IsolationForest

            forest = IsolationForest(n_estimators=64, random_state=20260422)
            forest.fit(features.reshape(-1, features.shape[-1]))
            return float(forest.score_samples(features)[0]), "sklearn_isoforest"
        except Exception:
            return 0.0, "na"
