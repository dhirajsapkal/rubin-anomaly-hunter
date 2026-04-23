"""Two-stage watch-list gate (ADR-0005).

This is the glue that runs both scoring modules against a linked tracklet
and writes the resulting watch-list decision into the detection DB.

STRICT invariant (ADR-0005): this module NEVER writes a row with
``status = 'promoted'``. Promotion to candidate requires external
follow-up evidence that a human attaches via the dashboard — that write
lands in the ``decisions`` table, not here. Any future code path that
tries to set status='promoted' from this module must fail audit.

Schema assumptions
------------------
The data-layer agent owns the SQLite schema. At the time this file was
written (2026-04-22) that schema did not yet exist in-repo. We assume
reasonable table shapes below and flag them here so the data-layer
agent can reconcile:

    tracklets(tracklet_id TEXT PRIMARY KEY, ...orbit_fit_id FK...)
    orbit_fits(orbit_fit_id INTEGER PK, tracklet_id FK, a REAL, e REAL,
               i REAL, q REAL, Q REAL, Omega REAL, omega REAL,
               A1 REAL, A2 REAL, A3 REAL, sigma_e REAL, sigma_A1 REAL,
               sigma_A2 REAL, sigma_A3 REAL, fit_rms REAL, n_obs INT,
               software_version TEXT, covariance_json TEXT, epoch_mjd REAL,
               mode TEXT)
    watch_list(watch_list_id INTEGER PK, tracklet_id TEXT FK,
               orbit_fit_id INT FK, category TEXT CHECK
               (category IN ('dark_comet','iso','both','none')),
               status TEXT CHECK (status IN ('watch','rejected','requeue')),
               confidence REAL, reasons TEXT, null_tests_json TEXT,
               thresholds_version TEXT, decided_at_utc TEXT)

If the real schema differs, adjust the SQL in `_insert_watch_list_row`;
no other module depends on the column names.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from rubin_hunter.config import Thresholds
from rubin_hunter.gate.null_tests import NullTestResult, run_null_tests
from rubin_hunter.linking.heliolinc3d_wrapper import Tracklet
from rubin_hunter.orbit.find_orb_wrapper import OrbitFit
from rubin_hunter.scoring.dark_comet import DarkCometScore, score_dark_comet
from rubin_hunter.scoring.iso import ISOScore, score_iso

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


@dataclass
class WatchListDecision:
    tracklet_id: str
    orbit_fit_id: int | None
    category: str  # "dark_comet", "iso", "both", "none"
    status: str  # "watch", "rejected", "requeue"
    confidence: float
    reasons: list[str]
    null_tests: dict[str, NullTestResult] = field(default_factory=dict)
    dark_comet_score: DarkCometScore | None = None
    iso_score: ISOScore | None = None
    thresholds_version: str = ""

    def to_log(self) -> dict[str, Any]:
        return {
            "tracklet_id": self.tracklet_id,
            "orbit_fit_id": self.orbit_fit_id,
            "category": self.category,
            "status": self.status,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "dark_comet": self.dark_comet_score.as_row() if self.dark_comet_score else None,
            "iso": self.iso_score.as_row() if self.iso_score else None,
            "null_tests": {k: asdict(v) for k, v in self.null_tests.items()},
            "thresholds_version": self.thresholds_version,
        }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def evaluate_tracklet(
    tracklet_id: int | str,
    conn: sqlite3.Connection,
    thresholds: Thresholds,
    *,
    morphology_override: dict | None = None,
) -> WatchListDecision:
    """Run the common gate + both scoring modules for a single tracklet,
    insert into the watch_list table, and return a structured decision.

    Reads the tracklet + latest orbit_fit from the DB. ``morphology`` is
    pulled from the morphology table if present; otherwise an empty dict
    is passed so the stubs pass through. Callers may pass
    ``morphology_override`` directly for tests.
    """
    prior_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        return _evaluate_tracklet_inner(tracklet_id, conn, thresholds, morphology_override)
    finally:
        conn.row_factory = prior_factory


def _evaluate_tracklet_inner(
    tracklet_id: int | str,
    conn: sqlite3.Connection,
    thresholds: Thresholds,
    morphology_override: dict | None,
) -> WatchListDecision:
    tracklet_row = _fetch_tracklet(conn, tracklet_id)
    if tracklet_row is None:
        raise ValueError(f"tracklet_id={tracklet_id!r} not in tracklets table")

    orbit_row = _fetch_latest_orbit_fit(conn, tracklet_id)
    if orbit_row is None:
        raise ValueError(
            f"no orbit_fits row for tracklet_id={tracklet_id!r}; "
            "fit the orbit before evaluating the gate"
        )

    tracklet = _tracklet_from_row(tracklet_row)
    orbit_fit = _orbit_fit_from_row(orbit_row)
    morphology = morphology_override or _fetch_morphology(conn, tracklet_id)

    # ---- Common gate (cheap, checked first) ------------------------------
    common_ok, common_reasons = _check_common_gate(tracklet, orbit_fit, thresholds)

    # ---- Always run both scorers for audit; gate status depends on
    # common gate AND score pass AND null tests (where relevant). --------
    dc_score = score_dark_comet(orbit_fit, morphology, thresholds.dark_comet)
    iso_score = score_iso(orbit_fit, thresholds.iso)

    # ---- Null-hypothesis tests -------------------------------------------
    null_tests = run_null_tests(tracklet, orbit_fit, morphology)

    # ---- Aggregate into a single category/status -------------------------
    decision = _aggregate(
        tracklet=tracklet,
        orbit_fit=orbit_fit,
        common_ok=common_ok,
        common_reasons=common_reasons,
        dc=dc_score,
        iso_res=iso_score,
        null_tests=null_tests,
        thresholds_version=thresholds.schema_version,
    )

    # ---- Persist to watch_list table -------------------------------------
    _insert_watch_list_row(conn, decision)
    return decision


# ---------------------------------------------------------------------------
# Common gate
# ---------------------------------------------------------------------------


def _check_common_gate(
    tracklet: Tracklet, orbit_fit: OrbitFit, thresholds: Thresholds
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    c = thresholds.common

    n_det_ok = tracklet.n_detections >= c.min_detections_per_tracklet
    reasons.append(
        f"n_detections={tracklet.n_detections} "
        f"(min {c.min_detections_per_tracklet}) {'ok' if n_det_ok else 'FAIL'}"
    )

    n_nights_ok = tracklet.n_nights >= c.min_nights_spanned
    reasons.append(
        f"n_nights={tracklet.n_nights} "
        f"(min {c.min_nights_spanned}) {'ok' if n_nights_ok else 'FAIL'}"
    )

    return n_det_ok and n_nights_ok, reasons


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _aggregate(
    *,
    tracklet: Tracklet,
    orbit_fit: OrbitFit,
    common_ok: bool,
    common_reasons: list[str],
    dc: DarkCometScore,
    iso_res: ISOScore,
    null_tests: dict[str, NullTestResult],
    thresholds_version: str,
) -> WatchListDecision:
    null_failed = [t for t in null_tests.values() if not t.passed and t.severity == "reject"]
    null_warn = [t for t in null_tests.values() if not t.passed and t.severity == "warn"]

    reasons: list[str] = []
    reasons.extend(common_reasons)
    reasons.append(f"dark_comet_gates={dc.gates}")
    reasons.append(f"iso_gates={iso_res.gates}")
    if null_failed:
        reasons.append(
            "null tests rejected: " + ", ".join(t.name for t in null_failed)
        )
    if null_warn:
        reasons.append("null tests warn: " + ", ".join(t.name for t in null_warn))
    if iso_res.refused:
        reasons.append("ISO refused per ADR-0005 (sigma_e too large)")

    # Decide category + status.
    if not common_ok or null_failed:
        category = "none"
        status = "rejected"
    elif null_warn:
        category = "none"
        status = "requeue"
    else:
        dc_pass = dc.passes
        iso_pass = iso_res.passes and not iso_res.refused
        if dc_pass and iso_pass:
            category, status = "both", "watch"
        elif dc_pass:
            category, status = "dark_comet", "watch"
        elif iso_pass:
            category, status = "iso", "watch"
        else:
            category, status = "none", "rejected"

    # Confidence: take the winning scorer if one passed; else max.
    if category == "dark_comet":
        confidence = dc.confidence
    elif category == "iso":
        confidence = iso_res.confidence
    elif category == "both":
        confidence = max(dc.confidence, iso_res.confidence)
    else:
        confidence = max(dc.confidence, iso_res.confidence, 0.0)

    # INVARIANT: never emit 'promoted' from this module. Assert defensively.
    assert status != "promoted", "ADR-0005: watch_list gate must not promote"

    return WatchListDecision(
        tracklet_id=str(tracklet.tracklet_id),
        orbit_fit_id=getattr(orbit_fit, "_db_id", None),
        category=category,
        status=status,
        confidence=float(confidence),
        reasons=reasons,
        null_tests=null_tests,
        dark_comet_score=dc,
        iso_score=iso_res,
        thresholds_version=thresholds_version,
    )


# ---------------------------------------------------------------------------
# SQLite I/O
# ---------------------------------------------------------------------------


def _fetch_tracklet(conn: sqlite3.Connection, tid: int | str) -> sqlite3.Row | None:
    cur = conn.execute("SELECT * FROM tracklets WHERE tracklet_id = ?", (str(tid),))
    return cur.fetchone()


def _fetch_latest_orbit_fit(
    conn: sqlite3.Connection, tid: int | str
) -> sqlite3.Row | None:
    cur = conn.execute(
        "SELECT * FROM orbit_fits WHERE tracklet_id = ? "
        "ORDER BY orbit_fit_id DESC LIMIT 1",
        (str(tid),),
    )
    return cur.fetchone()


def _fetch_morphology(conn: sqlite3.Connection, tid: int | str) -> dict:
    """Pull morphology from any morphology table if present. Fails open
    — returns {} when no table exists, which pushes us into stub-null-tests
    territory and passes the morphology gates only if extendedness==0."""
    try:
        cur = conn.execute(
            "SELECT extendedness, coma_flag, tail_flag, reliability, streak_flag "
            "FROM morphology WHERE tracklet_id = ? LIMIT 1",
            (str(tid),),
        )
        row = cur.fetchone()
        if row is None:
            return {}
        return {k: row[k] for k in row.keys()}
    except sqlite3.OperationalError:
        return {}


def _tracklet_from_row(row: sqlite3.Row) -> Tracklet:
    keys = row.keys()
    get = lambda k, d=None: row[k] if k in keys else d  # noqa: E731
    return Tracklet(
        tracklet_id=str(get("tracklet_id")),
        detection_ids=json.loads(get("detection_ids_json", "[]")) if "detection_ids_json" in keys else [],
        n_detections=int(get("n_detections", 0) or 0),
        n_nights=int(get("n_nights", 0) or 0),
        mjd_start=float(get("mjd_start", 0.0) or 0.0),
        mjd_end=float(get("mjd_end", 0.0) or 0.0),
        mean_ra_deg=float(get("mean_ra_deg", 0.0) or 0.0),
        mean_dec_deg=float(get("mean_dec_deg", 0.0) or 0.0),
        mean_motion_arcsec_hr=float(get("mean_motion_arcsec_hr", 0.0) or 0.0),
        quality_flag=str(get("quality_flag", "ok") or "ok"),
        source=str(get("source", "unknown") or "unknown"),
    )


def _orbit_fit_from_row(row: sqlite3.Row) -> OrbitFit:
    """Read an orbit_fits row, tolerating case-insensitive / aliased column
    names. SQLite itself is case-insensitive on identifiers, so the data
    layer must store `Omega`/`omega` under distinct names (e.g.
    `node_deg` + `arg_peri_deg` or `Omega_node_deg` + `omega_peri_deg`).
    We accept any of several common conventions."""
    raw = {k.lower(): row[k] for k in row.keys()}

    def pick(candidates: list[str], default: float = 0.0) -> float:
        for c in candidates:
            if c.lower() in raw and raw[c.lower()] is not None:
                try:
                    return float(raw[c.lower()])
                except (TypeError, ValueError):
                    pass
        return default

    def pick_str(candidates: list[str], default: str = "db") -> str:
        for c in candidates:
            if c.lower() in raw and raw[c.lower()] is not None:
                return str(raw[c.lower()])
        return default

    cov_raw = raw.get("covariance_json") or raw.get("covariance") or "[]"
    try:
        cov = json.loads(cov_raw) if isinstance(cov_raw, str) else cov_raw
    except Exception:
        cov = []

    fit = OrbitFit(
        a=pick(["a", "semi_major_axis_au"]),
        e=pick(["e", "eccentricity"]),
        i=pick(["i", "incl_deg", "inclination"]),
        q=pick(["q", "perihelion_au"]),
        Q=pick(["Q_aphelion", "aphelion_au", "Q"], default=float("nan")),
        Omega=pick(["node_deg", "Omega_node_deg", "ascending_node_deg", "Omega"]),
        omega=pick(["arg_peri_deg", "omega_peri_deg", "argument_of_perihelion_deg", "omega"]),
        A1=pick(["A1", "a1"]),
        A2=pick(["A2", "a2"]),
        A3=pick(["A3", "a3"]),
        sigma_a=pick(["sigma_a"]),
        sigma_e=pick(["sigma_e"]),
        sigma_i=pick(["sigma_i"]),
        sigma_q=pick(["sigma_q"]),
        sigma_Q=pick(["sigma_Q_aphelion", "sigma_aphelion", "sigma_Q"]),
        sigma_Omega=pick(["sigma_node_deg", "sigma_Omega_node", "sigma_Omega"]),
        sigma_omega=pick(["sigma_arg_peri_deg", "sigma_omega_peri", "sigma_omega"]),
        sigma_A1=pick(["sigma_A1"]),
        sigma_A2=pick(["sigma_A2"]),
        sigma_A3=pick(["sigma_A3"]),
        fit_rms=pick(["fit_rms", "rms_arcsec"]),
        n_obs=int(pick(["n_obs", "nobs"], default=0)),
        software_version=pick_str(["software_version", "version"]),
        covariance_matrix=cov if isinstance(cov, list) else [],
        mode=pick_str(["mode"], default="db"),
        epoch_mjd=pick(["epoch_mjd", "epoch"], default=float("nan")) or None,
    )
    fit._db_id = int(raw["orbit_fit_id"]) if "orbit_fit_id" in raw else None  # type: ignore[attr-defined]
    return fit


def _insert_watch_list_row(
    conn: sqlite3.Connection, decision: WatchListDecision
) -> None:
    null_tests_json = json.dumps(
        {k: asdict(v) for k, v in decision.null_tests.items()}, default=str
    )
    reasons_text = " | ".join(decision.reasons)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ADR-0005 invariant check — cannot be bypassed.
    if decision.status == "promoted":
        raise RuntimeError(
            "ADR-0005 violation: watch_list gate attempted to insert "
            "status='promoted'. Promotion is dashboard-only."
        )

    try:
        conn.execute(
            """
            INSERT INTO watch_list
              (tracklet_id, orbit_fit_id, category, status, confidence,
               reasons, null_tests_json, thresholds_version, decided_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.tracklet_id,
                decision.orbit_fit_id,
                decision.category,
                decision.status,
                decision.confidence,
                reasons_text,
                null_tests_json,
                decision.thresholds_version,
                now,
            ),
        )
        conn.commit()
    except sqlite3.OperationalError as exc:
        # The data-layer agent's schema may differ; log but don't crash
        # the pipeline — evaluation still succeeded, persistence didn't.
        logger.error(
            "Could not insert watch_list row (schema mismatch?): %s. "
            "Decision payload: %s",
            exc,
            decision.to_log(),
        )
