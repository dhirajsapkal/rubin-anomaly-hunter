"""Generate a realistic-feeling demo SQLite DB for the dashboard.

This module is **data-only**: it never invokes ``find_orb`` or
``heliolinc3d`` and never depends on those being installed. It produces
plausible-looking outputs of what those tools would have produced,
stored in the schema defined by
:mod:`rubin_hunter.detection_db.schema`.

What gets generated
-------------------
Per the spec in the caller's task:

* ~2000 routine asteroid/NEO tracklets with bound orbit fits
  (e < 0.8, typical inclination distributions).
* ~150 tracklets rejected by the pipeline (artifact / streak / CR).
* 4 dark-comet watch-list entries spread over the last 14 nights,
  non-grav residuals above threshold.
* 1 ISO watch-list entry seeded from the published 3I/ATLAS orbit
  (e ≈ 6.2, q ≈ 1.36 AU, i ≈ 175°) — given a mysterious internal id.
  The MPC-crossmatch note calls out that this matches the known orbit of
  3I/ATLAS within tolerance (likely rediscovery) — per ADR-0005 a
  watch-list entry is never a discovery claim.
* Historical archive: 2 accepted, 3 rejected, 1 promoted, all dated
  back ~30 days.
* Pipeline health: 14 nights of ingest counts, linking stats, fit
  success rates.
* Each watch-list entry has a tracklet with ≥5 detections across ≥3
  nights and a plausible-covariance orbit fit. One dark-comet entry is
  deliberately ambiguous (threshold-adjacent), to show the "defer"
  action in the UI. One has a suspicious-chip-correlation null-test
  failure, to show the UI for that case.

Determinism
-----------
The generator wipes and rewrites the target DB on every run, seeded
from ``config.anomaly_score.random_seed``. Re-running produces an
identical file modulo floating-point drift.

Language discipline
-------------------
Per ADR-0005 and CLAUDE.md, this generator must never write "candidate"
status for an entry that has not been explicitly promoted through the
two-stage gate. The 3I/ATLAS-alike entry stays at ``status='new'`` with
a teaching note — it is **not** marked as a discovery.
"""

from __future__ import annotations

import json
import math
import random
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rubin_hunter.config import Thresholds, load_thresholds
from rubin_hunter.detection_db.healpix_index import bucket
from rubin_hunter.detection_db.schema import connect, init_db


# ---------------------------------------------------------------------------
# paths + constants
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DEMO_DB_PATH = _PROJECT_ROOT / "data" / "demo.sqlite"

_SOFTWARE_VERSION = "find_orb-demo-0.1.0"
_CONFIG_TAG = "thresholds-commissioning"
_GIT_COMMIT = "demo000000"  # placeholder until real git integration
_NOW_UTC = datetime(2026, 4, 22, 3, 0, 0, tzinfo=timezone.utc)

# Number of routine objects to fabricate. These are what a typical
# early-ops night looks like: a few thousand plain asteroids with
# clean orbit fits.
N_ROUTINE_TRACKLETS = 2000
N_REJECTED_TRACKLETS = 150


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
@dataclass
class _Detection:
    alert_id: str
    ra: float
    dec: float
    mjd: float
    band: str
    psf_flux: float
    psf_flux_err: float
    snr: float
    reliability: float
    streak_flag: int
    ingest_time_utc: datetime


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _mjd_from_datetime(dt: datetime) -> float:
    # MJD 51544.0 = 2000-01-01T00:00:00 UTC.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = dt - datetime(2000, 1, 1, tzinfo=timezone.utc)
    return 51544.0 + delta.total_seconds() / 86400.0


def _sample_band(rng: random.Random) -> str:
    return rng.choices(
        population=["u", "g", "r", "i", "z", "y"],
        weights=[0.05, 0.25, 0.35, 0.20, 0.10, 0.05],
    )[0]


def _sample_inclination(rng: random.Random) -> float:
    """Rayleigh-ish inclination distribution peaking around 5-15 deg."""
    i = rng.gauss(8.0, 6.0)
    return max(0.1, min(abs(i), 35.0))


def _sample_eccentricity_bound(rng: random.Random) -> float:
    e = abs(rng.gauss(0.15, 0.12))
    return min(e, 0.79)


def _sample_semimajor(rng: random.Random) -> float:
    # Main-belt-ish, with a tail to NEO and Centaur.
    return rng.choices(
        population=[rng.uniform(1.0, 1.5), rng.uniform(2.0, 3.3), rng.uniform(3.3, 5.5)],
        weights=[0.1, 0.75, 0.15],
    )[0]


def _sample_ra_dec(rng: random.Random) -> tuple[float, float]:
    ra = rng.uniform(0.0, 360.0)
    # Cosine-weighted for even sphere coverage.
    u = rng.uniform(-1.0, 1.0)
    dec = math.degrees(math.asin(u))
    return ra, dec


# ---------------------------------------------------------------------------
# detection / tracklet builders
# ---------------------------------------------------------------------------
def _make_tracklet_detections(
    rng: random.Random,
    ra0: float,
    dec0: float,
    n_detections: int,
    n_nights: int,
    base_date: datetime,
    *,
    streak_flag: bool = False,
    reliability_mean: float = 0.9,
) -> list[_Detection]:
    """Fabricate ``n_detections`` detections of one object across ``n_nights``.

    Positions drift linearly in RA/Dec across nights to mimic a slow
    solar-system mover; intra-night jitter is a few arcsec, inter-night
    drift is ~arcmin.
    """
    detections: list[_Detection] = []
    # Per-night drift in arcmin for RA / Dec — positive or negative.
    ra_drift_arcmin_per_night = rng.uniform(-5.0, 5.0)
    dec_drift_arcmin_per_night = rng.uniform(-5.0, 5.0)

    # Distribute n_detections across n_nights as evenly as possible:
    # base + one extra for the first `remainder` nights.
    base_per_night, remainder = divmod(n_detections, n_nights)
    allocation = [base_per_night + (1 if k < remainder else 0) for k in range(n_nights)]

    det_idx = 0
    for night_idx in range(n_nights):
        n_this_night = allocation[night_idx]
        night_t = base_date + timedelta(days=night_idx)
        for _k in range(n_this_night):
            if det_idx >= n_detections:
                break
            # within-night drift, few arcsec
            dra = rng.gauss(0.0, 2.0) / 3600.0
            ddec = rng.gauss(0.0, 2.0) / 3600.0
            ra = (
                ra0
                + (night_idx * ra_drift_arcmin_per_night / 60.0)
                + dra
            ) % 360.0
            dec = max(-89.5, min(89.5,
                dec0
                + (night_idx * dec_drift_arcmin_per_night / 60.0)
                + ddec,
            ))
            obs_time = night_t + timedelta(hours=rng.uniform(0.0, 6.0))
            reliability = max(0.0, min(1.0, rng.gauss(reliability_mean, 0.04)))
            snr = max(5.0, rng.gauss(18.0, 6.0))
            psf_flux = max(1e-2, rng.gauss(50.0, 20.0))
            detections.append(
                _Detection(
                    alert_id=f"alert_{rng.randrange(10**9, 10**10):010x}",
                    ra=ra,
                    dec=dec,
                    mjd=_mjd_from_datetime(obs_time),
                    band=_sample_band(rng),
                    psf_flux=psf_flux,
                    psf_flux_err=max(1e-3, psf_flux * 0.08),
                    snr=snr,
                    reliability=reliability,
                    streak_flag=1 if streak_flag and rng.random() < 0.7 else 0,
                    ingest_time_utc=obs_time,
                )
            )
            det_idx += 1
    return detections


def _insert_detections(conn: sqlite3.Connection, dets: list[_Detection]) -> list[int]:
    ids: list[int] = []
    cur = conn.cursor()
    for d in dets:
        cur.execute(
            """
            INSERT INTO detections(
                alert_id, ra, dec, mjd, band, psf_flux, psf_flux_err,
                snr, reliability, streak_flag, healpix_bucket, ingest_time_utc
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                d.alert_id,
                d.ra,
                d.dec,
                d.mjd,
                d.band,
                d.psf_flux,
                d.psf_flux_err,
                d.snr,
                d.reliability,
                d.streak_flag,
                bucket(d.ra, d.dec),
                _iso(d.ingest_time_utc),
            ),
        )
        ids.append(cur.lastrowid or -1)
    return ids


def _insert_tracklet(
    conn: sqlite3.Connection,
    detection_ids: list[int],
    n_nights: int,
    total_arc_hours: float,
    created_utc: datetime,
) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tracklets(detection_ids_json, num_nights, total_arc_hours, created_utc)
        VALUES (?,?,?,?)
        """,
        (json.dumps(detection_ids), n_nights, total_arc_hours, _iso(created_utc)),
    )
    return cur.lastrowid or -1


def _insert_orbit_fit(
    conn: sqlite3.Connection,
    tracklet_id: int,
    *,
    a: float | None,
    e: float | None,
    i: float | None,
    q: float | None,
    Q: float | None,
    A1: float | None,
    A2: float | None,
    A3: float | None,
    sigma_e: float | None,
    sigma_A1: float | None,
    sigma_A2: float | None,
    sigma_A3: float | None,
    fit_rms: float,
    n_obs: int,
    fit_time: datetime,
) -> int:
    # Column names are de-collision-ed (see schema comment): a -> a_au,
    # i -> incl_deg, q -> q_au, Q -> Q_au. The Python kwargs still use
    # the astronomy-symbol names so callers can read the code naturally.
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO orbit_fits(
            tracklet_id, a_au, e, incl_deg, perihelion_au, aphelion_au,
            A1, A2, A3, sigma_e, sigma_A1, sigma_A2, sigma_A3,
            fit_rms, n_obs, software_version, fit_time_utc
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            tracklet_id, a, e, i, q, Q, A1, A2, A3,
            sigma_e, sigma_A1, sigma_A2, sigma_A3,
            fit_rms, n_obs, _SOFTWARE_VERSION, _iso(fit_time),
        ),
    )
    return cur.lastrowid or -1


# ---------------------------------------------------------------------------
# phases of the generator
# ---------------------------------------------------------------------------
def _seed_threshold_version(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO threshold_versions(
            config_tag, git_commit, locked, first_seen_utc
        ) VALUES (?,?,?,?)
        """,
        (_CONFIG_TAG, _GIT_COMMIT, 0, _iso(_NOW_UTC)),
    )
    row = conn.execute(
        "SELECT version_id FROM threshold_versions WHERE config_tag=? AND git_commit=?",
        (_CONFIG_TAG, _GIT_COMMIT),
    ).fetchone()
    return int(row[0])


def _seed_pipeline_health(conn: sqlite3.Connection, rng: random.Random) -> None:
    """14 nights of nightly pipeline-health metrics."""
    cur = conn.cursor()
    for night_offset in range(14, 0, -1):
        night_date = (_NOW_UTC - timedelta(days=night_offset)).date().isoformat()
        alerts = rng.randint(650_000, 950_000)
        sso = int(alerts * rng.uniform(0.0008, 0.0015))
        linked = int(sso * rng.uniform(0.55, 0.75))
        fits_ok = int(linked * rng.uniform(0.75, 0.90))
        fits_failed = max(0, linked - fits_ok)
        dropped = int(alerts * rng.uniform(0.0, 0.0008))
        lag = rng.uniform(12.0, 55.0)
        cur.execute(
            """
            INSERT OR REPLACE INTO pipeline_health(
                obs_night, alerts_ingested, sso_candidates,
                tracklets_linked, orbit_fits_ok, orbit_fits_failed,
                dropped_alerts, ingest_lag_s_p95, notes
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (night_date, alerts, sso, linked, fits_ok, fits_failed,
             dropped, lag, None),
        )


def _seed_routine_tracklets(
    conn: sqlite3.Connection, rng: random.Random, threshold_version_id: int
) -> None:
    """Bulk-fabricate the routine asteroid/NEO population."""
    for _n in range(N_ROUTINE_TRACKLETS):
        ra0, dec0 = _sample_ra_dec(rng)
        n_nights = rng.choice([1, 2, 3, 3, 4])
        n_det = n_nights * rng.choice([2, 3])
        # base date within the last 14 nights
        base = _NOW_UTC - timedelta(days=rng.randint(1, 14))
        dets = _make_tracklet_detections(
            rng, ra0, dec0, n_det, n_nights, base, reliability_mean=0.91
        )
        det_ids = _insert_detections(conn, dets)
        arc_hours = (max(d.mjd for d in dets) - min(d.mjd for d in dets)) * 24.0
        tid = _insert_tracklet(conn, det_ids, n_nights, arc_hours, base)
        a = _sample_semimajor(rng)
        e = _sample_eccentricity_bound(rng)
        incl = _sample_inclination(rng)
        q = a * (1 - e)
        Q = a * (1 + e)
        _insert_orbit_fit(
            conn, tid,
            a=a, e=e, i=incl, q=q, Q=Q,
            A1=None, A2=None, A3=None,
            sigma_e=rng.uniform(0.005, 0.03),
            sigma_A1=None, sigma_A2=None, sigma_A3=None,
            fit_rms=rng.uniform(0.15, 0.6),
            n_obs=len(dets),
            fit_time=base + timedelta(hours=2),
        )


def _seed_rejected_tracklets(
    conn: sqlite3.Connection, rng: random.Random
) -> None:
    """Tracklets that the pipeline would reject (artifact / streak / CR)."""
    for _n in range(N_REJECTED_TRACKLETS):
        ra0, dec0 = _sample_ra_dec(rng)
        n_nights = rng.choice([1, 1, 2])
        n_det = rng.choice([2, 3, 4])
        base = _NOW_UTC - timedelta(days=rng.randint(1, 14))
        dets = _make_tracklet_detections(
            rng, ra0, dec0, n_det, n_nights, base,
            streak_flag=True, reliability_mean=0.35,
        )
        det_ids = _insert_detections(conn, dets)
        arc_hours = max(0.0, (max(d.mjd for d in dets) - min(d.mjd for d in dets)) * 24.0)
        tid = _insert_tracklet(conn, det_ids, n_nights, arc_hours, base)
        # No orbit fit or a failed-looking one; keep an empty row with
        # only fit_rms set high to show the fit failed.
        _insert_orbit_fit(
            conn, tid,
            a=None, e=None, i=None, q=None, Q=None,
            A1=None, A2=None, A3=None,
            sigma_e=None, sigma_A1=None, sigma_A2=None, sigma_A3=None,
            fit_rms=rng.uniform(2.5, 9.0),
            n_obs=len(dets),
            fit_time=base + timedelta(hours=2),
        )


def _insert_watch_entry(
    conn: sqlite3.Connection,
    category: str,
    tracklet_id: int,
    orbit_fit_id: int,
    created_utc: datetime,
    status: str,
    null_test_results: dict,
    mpc_crossmatch: str | None,
    notes: str | None,
    threshold_version_id: int,
) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO watch_list(
            category, tracklet_id, orbit_fit_id, created_utc,
            status, null_test_results_json, mpc_crossmatch,
            notes, threshold_version_id
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            category, tracklet_id, orbit_fit_id, _iso(created_utc), status,
            json.dumps(null_test_results),
            mpc_crossmatch, notes, threshold_version_id,
        ),
    )
    return cur.lastrowid or -1


def _passing_null_tests() -> dict:
    # See PRD §10 for the canonical null-hypothesis test list.
    return {
        "known_sso_match": "pass",
        "cometary_outgassing_consistent": "pass",
        "image_artifact": "pass",
        "streak_residual": "pass",
        "short_arc_ambiguity": "pass",
        "instrument_systematic": "pass",
        "broker_flag_drift": "pass",
    }


def _seed_dark_comet_watchlist(
    conn: sqlite3.Connection,
    rng: random.Random,
    thresholds: Thresholds,
    threshold_version_id: int,
) -> None:
    """4 dark-comet entries spread over the last 14 nights.

    One is threshold-adjacent (to show the "defer" action); one has a
    suspicious chip-correlation null-test failure.
    """
    specs = [
        # (days_back, e, i, A1_scale, A2_scale, A3_scale, rel_sigma, extra_note, null_tweak)
        # Clean strong detections:
        (13, 0.52, 12.3, 4.5, 2.1, 0.8, 0.18, None, None),
        (9,  0.31, 6.7, 3.2, 1.4, 0.6, 0.22, None, None),
        # Threshold-wobbler — natural "defer" case:
        (4,  0.44, 9.8, 1.15, 1.05, 0.9, 0.47,
         "non-grav magnitude sits right on A_min; sigma/|A| near max tolerance", "defer-hint"),
        # Suspicious chip correlation — UI must show that:
        (2,  0.28, 4.5, 3.8, 2.4, 1.1, 0.20,
         "possible chip correlation with detector R42_S12 across last 4 nights", "chip"),
    ]
    dark = thresholds.dark_comet
    for days_back, e, i, a1s, a2s, a3s, rel_sigma, note, null_tweak in specs:
        ra0, dec0 = _sample_ra_dec(rng)
        base = _NOW_UTC - timedelta(days=days_back)
        n_nights = rng.choice([3, 4, 4])
        n_det = max(5, n_nights * 2)
        dets = _make_tracklet_detections(
            rng, ra0, dec0, n_det, n_nights, base, reliability_mean=0.93
        )
        det_ids = _insert_detections(conn, dets)
        arc_hours = (max(d.mjd for d in dets) - min(d.mjd for d in dets)) * 24.0
        tid = _insert_tracklet(conn, det_ids, n_nights, arc_hours, base)

        a = rng.uniform(2.1, 3.2)
        A1 = dark.A1_min_au_per_day2 * a1s
        A2 = dark.A2_min_au_per_day2 * a2s
        A3 = dark.A3_min_au_per_day2 * a3s
        sigma_A1 = abs(A1) * rel_sigma
        sigma_A2 = abs(A2) * rel_sigma
        sigma_A3 = abs(A3) * rel_sigma
        sigma_e = rng.uniform(0.015, 0.04)
        fit_id = _insert_orbit_fit(
            conn, tid,
            a=a, e=e, i=i, q=a * (1 - e), Q=a * (1 + e),
            A1=A1, A2=A2, A3=A3,
            sigma_e=sigma_e,
            sigma_A1=sigma_A1, sigma_A2=sigma_A2, sigma_A3=sigma_A3,
            fit_rms=rng.uniform(0.25, 0.55),
            n_obs=len(dets),
            fit_time=base + timedelta(hours=2),
        )

        null_results = _passing_null_tests()
        if null_tweak == "chip":
            null_results["instrument_systematic"] = (
                "suspicious — >80% of detections land on detector R42_S12 "
                "across 4 nights; investigate camera systematic before promoting"
            )

        status = "new"
        notes = note
        if null_tweak == "defer-hint":
            notes = (note or "") + " | candidate for 'defer' action on review"

        _insert_watch_entry(
            conn,
            category="dark_comet",
            tracklet_id=tid,
            orbit_fit_id=fit_id,
            created_utc=base + timedelta(hours=3),
            status=status,
            null_test_results=null_results,
            mpc_crossmatch="no match within 30 arcsec",
            notes=notes,
            threshold_version_id=threshold_version_id,
        )


def _seed_iso_watchlist(
    conn: sqlite3.Connection,
    rng: random.Random,
    thresholds: Thresholds,
    threshold_version_id: int,
) -> None:
    """1 ISO entry seeded from the 3I/ATLAS published orbit.

    Per ADR-0005 this is **watch-list only**. The MPC-crossmatch note
    makes it clear that this matches the known orbit of 3I/ATLAS within
    tolerance — it is a rediscovery, not a new discovery claim.
    """
    # Position roughly compatible with 3I/ATLAS's Rubin-commissioning
    # observations — exact values are unimportant for the demo.
    ra0 = rng.uniform(285.0, 295.0)
    dec0 = rng.uniform(-30.0, -20.0)
    base = _NOW_UTC - timedelta(days=5)
    n_nights = 4
    n_det = 8
    dets = _make_tracklet_detections(
        rng, ra0, dec0, n_det, n_nights, base, reliability_mean=0.96
    )
    # ISOs move fast relative to main-belt asteroids — bump up the drift.
    det_ids = _insert_detections(conn, dets)
    arc_hours = (max(d.mjd for d in dets) - min(d.mjd for d in dets)) * 24.0
    tid = _insert_tracklet(conn, det_ids, n_nights, arc_hours, base)

    # Published 3I/ATLAS orbital elements (approximate):
    #   e ≈ 6.2 (retrograde hyperbolic), q ≈ 1.36 AU, i ≈ 175°
    e = 6.2 + rng.gauss(0.0, 0.05)
    q = 1.36 + rng.gauss(0.0, 0.01)
    incl = 175.0 + rng.gauss(0.0, 0.2)
    # For hyperbolic: a = -q/(e-1); Q is undefined — leave NULL.
    a = -q / (e - 1)
    sigma_e = rng.uniform(0.12, 0.28)  # still above zero — short arc
    fit_id = _insert_orbit_fit(
        conn, tid,
        a=a, e=e, i=incl, q=q, Q=None,
        A1=None, A2=None, A3=None,
        sigma_e=sigma_e,
        sigma_A1=None, sigma_A2=None, sigma_A3=None,
        fit_rms=rng.uniform(0.22, 0.4),
        n_obs=len(dets),
        fit_time=base + timedelta(hours=2),
    )

    internal_id = "RH-OBJ-0x3A71A5AF"  # mysterious but clearly internal
    mpc_note = (
        "matches orbit of known ISO 3I/ATLAS within tolerance — likely "
        "rediscovery. Not a discovery claim (ADR-0005: watch-list only "
        "until external follow-up confirms)."
    )
    notes = (
        f"internal id: {internal_id}. Teaching case: the pipeline reached "
        "the ISO watch-list via retrograde hyperbolic best-fit + small "
        "sigma_e; without the MPC cross-match line this is exactly what "
        "a real ISO rediscovery looks like in Stage A."
    )
    _insert_watch_entry(
        conn,
        category="iso",
        tracklet_id=tid,
        orbit_fit_id=fit_id,
        created_utc=base + timedelta(hours=3),
        status="new",
        null_test_results=_passing_null_tests(),
        mpc_crossmatch=mpc_note,
        notes=notes,
        threshold_version_id=threshold_version_id,
    )


def _seed_historical_archive(
    conn: sqlite3.Connection,
    rng: random.Random,
    thresholds: Thresholds,
    threshold_version_id: int,
) -> None:
    """Six historical watch-list entries with prior decisions.

    2 accepted, 3 rejected, 1 promoted-to-candidate. All dated ~30 days
    back. "Promoted" means external follow-up arrived; we model that as
    a single audit-log decision row, per PRD §11.
    """
    plan = [
        ("dark_comet", "accept",  "follow-up observed by amateur network confirmed non-grav A1"),
        ("dark_comet", "accept",  "refit with 3-night extension held A2 above threshold"),
        ("dark_comet", "reject",  "null-hypothesis: streak residual identified on re-inspection"),
        ("iso",        "reject",  "null-hypothesis: short-arc ambiguity; sigma_e blew up on refit"),
        ("dark_comet", "reject",  "null-hypothesis: matches numbered asteroid on MPC xmatch refresh"),
        ("dark_comet", "promote", "external 4-night follow-up resolved non-grav signature"),
    ]

    for category, terminal_decision, decision_note in plan:
        days_back = rng.randint(25, 35)
        base = _NOW_UTC - timedelta(days=days_back)
        ra0, dec0 = _sample_ra_dec(rng)
        n_nights = 4
        n_det = rng.choice([6, 7, 8])
        dets = _make_tracklet_detections(
            rng, ra0, dec0, n_det, n_nights, base, reliability_mean=0.91
        )
        det_ids = _insert_detections(conn, dets)
        arc_hours = (max(d.mjd for d in dets) - min(d.mjd for d in dets)) * 24.0
        tid = _insert_tracklet(conn, det_ids, n_nights, arc_hours, base)

        if category == "dark_comet":
            a = rng.uniform(2.1, 3.4); e = rng.uniform(0.2, 0.6); incl = rng.uniform(3.0, 20.0)
            A1 = thresholds.dark_comet.A1_min_au_per_day2 * rng.uniform(2.0, 5.0)
            A2 = thresholds.dark_comet.A2_min_au_per_day2 * rng.uniform(1.5, 3.5)
            A3 = thresholds.dark_comet.A3_min_au_per_day2 * rng.uniform(0.5, 1.5)
            fit_id = _insert_orbit_fit(
                conn, tid,
                a=a, e=e, i=incl, q=a * (1 - e), Q=a * (1 + e),
                A1=A1, A2=A2, A3=A3,
                sigma_e=rng.uniform(0.01, 0.03),
                sigma_A1=abs(A1) * rng.uniform(0.15, 0.35),
                sigma_A2=abs(A2) * rng.uniform(0.15, 0.35),
                sigma_A3=abs(A3) * rng.uniform(0.15, 0.35),
                fit_rms=rng.uniform(0.2, 0.5),
                n_obs=len(dets),
                fit_time=base + timedelta(hours=2),
            )
        else:
            # hyperbolic
            e = rng.uniform(1.3, 2.5); q = rng.uniform(0.9, 2.2); incl = rng.uniform(30.0, 170.0)
            a = -q / (e - 1)
            fit_id = _insert_orbit_fit(
                conn, tid,
                a=a, e=e, i=incl, q=q, Q=None,
                A1=None, A2=None, A3=None,
                sigma_e=rng.uniform(0.2, 0.45),
                sigma_A1=None, sigma_A2=None, sigma_A3=None,
                fit_rms=rng.uniform(0.3, 0.6),
                n_obs=len(dets),
                fit_time=base + timedelta(hours=2),
            )

        # Status: "accept" / "reject" map 1:1; "promote" becomes the
        # terminal status "promoted" after a prior "accept".
        if terminal_decision == "promote":
            initial_status = "accept"
            final_status = "promoted"
        elif terminal_decision == "accept":
            initial_status = "accept"
            final_status = "accept"
        else:
            initial_status = "reject"
            final_status = "reject"

        entry_id = _insert_watch_entry(
            conn,
            category=category,
            tracklet_id=tid,
            orbit_fit_id=fit_id,
            created_utc=base + timedelta(hours=3),
            status=final_status,
            null_test_results=_passing_null_tests(),
            mpc_crossmatch="no match within 30 arcsec" if "MPC" not in decision_note else "match found on refresh",
            notes=f"historical entry; {decision_note}",
            threshold_version_id=threshold_version_id,
        )

        # Audit-log rows. Accept-first-then-promote gets two rows.
        cur = conn.cursor()
        if terminal_decision == "promote":
            cur.execute(
                "INSERT INTO decisions(entry_id, decision, note, decided_utc) VALUES (?,?,?,?)",
                (entry_id, "accept", "initial accept from Stage A review",
                 _iso(base + timedelta(hours=4))),
            )
            cur.execute(
                "INSERT INTO decisions(entry_id, decision, note, decided_utc) VALUES (?,?,?,?)",
                (entry_id, "promote", decision_note,
                 _iso(base + timedelta(days=5))),
            )
        else:
            cur.execute(
                "INSERT INTO decisions(entry_id, decision, note, decided_utc) VALUES (?,?,?,?)",
                (entry_id, initial_status, decision_note,
                 _iso(base + timedelta(hours=4))),
            )


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def generate(
    db_path: Path = DEFAULT_DEMO_DB_PATH,
    thresholds_path: Path | None = None,
) -> Path:
    """Wipe ``db_path`` and regenerate a full demo dataset.

    Returns the path to the newly created SQLite file. The generator is
    deterministic — with the same seed you get byte-identical row
    counts and effectively-identical numeric fields.
    """
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()
    # Remove any SQLite WAL/shm siblings from a prior run.
    for suffix in ("-wal", "-shm"):
        sibling = db_path.with_name(db_path.name + suffix)
        if sibling.exists():
            sibling.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    thresholds = load_thresholds(thresholds_path)
    rng = random.Random(thresholds.anomaly_score.random_seed)

    init_db(db_path)
    conn = connect(db_path)
    try:
        threshold_version_id = _seed_threshold_version(conn)
        _seed_pipeline_health(conn, rng)
        _seed_routine_tracklets(conn, rng, threshold_version_id)
        _seed_rejected_tracklets(conn, rng)
        _seed_dark_comet_watchlist(conn, rng, thresholds, threshold_version_id)
        _seed_iso_watchlist(conn, rng, thresholds, threshold_version_id)
        _seed_historical_archive(conn, rng, thresholds, threshold_version_id)
        conn.commit()
    finally:
        conn.close()

    return db_path


# Convenience CLI: `python -m rubin_hunter.demo.generate_demo_data`.
if __name__ == "__main__":  # pragma: no cover
    path = generate()
    print(f"demo DB written to {path}")
