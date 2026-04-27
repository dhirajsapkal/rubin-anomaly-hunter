"""End-to-end pipeline: ingest → detection DB → linking → orbit fit → gate.

This is the orchestrator for the M0-bridge milestone (ADR-0013). It wires:

    Lasair-LSST REST → RawAlertArchive (ADR-0009)
                     → detections / tracklets / orbit_fits / watch_list / pipeline_health
                     → dashboard (unchanged)

Three principles the orchestrator must honour:

1. **Raw persists first.** Every alert lands in the Parquet archive
   before any normalisation touches it. Reproducibility requires it
   (PRD §8 N5, ADR-0009).
2. **Two-stage gate is strict.** This module only ever writes
   watch_list.status values of ``new`` | ``defer`` | ``reject``. Never
   ``accept`` and never ``promoted`` — those are dashboard-only after
   human review (ADR-0005).
3. **Mock-mode is loud.** When heliolinc3d or find_orb are missing, the
   wrapper's own warning already fires; in addition we tag every orbit
   fit with ``software_version`` containing the word "mock" and record a
   pipeline-health row that counts mock fits separately from real ones.

Gate → schema.py status mapping
-------------------------------
`gate.watch_list.WatchListDecision.status` uses ``watch|rejected|requeue``
(from an older schema draft). This orchestrator translates into the
schema.py-enforced ``new|defer|reject|accept|promoted`` CHECK constraint:

    watch    → new       (enters the triage queue)
    requeue  → defer     (ambiguous — review later)
    rejected → reject

The orchestrator writes its own watch_list INSERTs directly — it does
not call `gate._insert_watch_list_row` because that targets a different
schema. The scoring + decision logic still goes through `gate.evaluate_*`.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from rubin_hunter.config import Thresholds, load_thresholds
from rubin_hunter.detection_db import healpix_index, schema
from rubin_hunter.gate.null_tests import run_null_tests
from rubin_hunter.ingest.fink_consumer import FinkConsumer
from rubin_hunter.ingest.fink_ingest import (
    alert_to_detections,
    broker_flags_from_alert,
)
from rubin_hunter.ingest.lasair_rest import (
    LasairObject,
    LasairPoll,
    LasairQuery,
    LasairRestConsumer,
)
from rubin_hunter.ingest.persistence import RawAlertArchive
from rubin_hunter.linking.heliolinc3d_wrapper import HelioLinC3DRunner, Tracklet
from rubin_hunter.orbit.find_orb_wrapper import FindOrbRunner, OrbitFit
from rubin_hunter.scoring.dark_comet import score_dark_comet
from rubin_hunter.scoring.iso import score_iso

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config wrapper
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_DB = _PROJECT_ROOT / "data" / "live.sqlite"
DEFAULT_ARCHIVE_ROOT = _PROJECT_ROOT / "data" / "archive"

# MPC site code for Rubin / LSST. Not all Lasair rows will carry this,
# but it's the right default for ADES output.
RUBIN_MPC_CODE = "X05"


@dataclass
class PipelineRunStats:
    """Returned from `run_once`. Summarises what went in and what came out."""

    poll_http_status: int
    objects_fetched: int
    detections_ingested: int
    tracklets_linked: int
    orbit_fits_ok: int
    orbit_fits_failed: int
    watch_list_new: int
    watch_list_deferred: int
    watch_list_rejected: int
    mock_mode_orbit: bool
    mock_mode_linking: bool
    obs_night: str
    notes: str = ""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_once(
    *,
    db_path: Path = DEFAULT_LIVE_DB,
    archive_root: Path = DEFAULT_ARCHIVE_ROOT,
    since_days: float = 1.0,
    min_det: int = 2,
    limit: int = 200,
    thresholds: Thresholds | None = None,
    lasair: LasairRestConsumer | None = None,
    lasair_token: str | None = None,
    ingest_mode: str = "lasair",
    fink_topic: str = "fink_uniform_sample_lsst",
    fink_group_id: str = "rubin-hunter-personal",
    fink_config_path: Path | None = None,
    fink_max_messages: int = 200,
    fink_timeout_s: float = 30.0,
    fink_offset_reset: str = "latest",
    fink_strict: bool = False,
) -> PipelineRunStats:
    """Run one ingest → gate cycle end-to-end.

    ``ingest_mode`` is ``"lasair"`` (default, ADR-0013 bridge) or ``"fink"``
    (ADR-0016, Kafka per-detection path). Fink mode needs a registered
    fink-client credentials YAML; if missing the consumer drops to
    offline sample replay and writes nothing.
    """
    thresholds = thresholds or load_thresholds()
    schema.init_db(db_path)

    _ensure_threshold_version_row(db_path, thresholds)

    poll_http_status = 0
    objects_fetched = 0
    detection_rows: list[dict[str, Any]] = []

    if ingest_mode == "fink":
        # 1. Ingest via Fink Kafka ---------------------------------------
        fink = FinkConsumer(
            topic=fink_topic,
            group_id=fink_group_id,
            config_path=fink_config_path,
            offset_reset=fink_offset_reset,
            strict=fink_strict,
        )
        logger.info("Fink consumer mode=%s topic=%s", fink.mode, fink_topic)

        alerts = fink.poll_batch(
            max_messages=fink_max_messages,
            timeout_s=fink_timeout_s,
        )
        fink.close()
        objects_fetched = len(alerts)
        # Fink doesn't have an HTTP status; surface 200 on success / 0 when the
        # consumer returned an empty list (offline/no-creds/no-messages).
        poll_http_status = 200 if alerts else 0

        # 2. Persist raw payloads before transformation (ADR-0009) -------
        with RawAlertArchive(archive_root) as archive:
            for alert in alerts:
                archive.append(
                    alert={**alert, "_source_topic": f"fink-kafka/{fink_topic}"},
                    broker_flags=broker_flags_from_alert(alert),
                    ingest_time=datetime.now(timezone.utc),
                )

        # 3. Normalise each alert into per-detection rows ----------------
        for alert in alerts:
            for row in alert_to_detections(alert):
                row["healpix_bucket"] = healpix_index.bucket(
                    float(row["ra"]), float(row["dec"])
                )
                detection_rows.append(row)
    else:
        # ADR-0013 Lasair REST path (default).
        lasair = lasair or LasairRestConsumer(token=lasair_token)
        since_mjd = _now_mjd() - since_days
        query = LasairQuery(since_mjd=since_mjd, min_det=min_det, limit=limit)
        poll = lasair.run_filter(query)
        poll_http_status = poll.http_status
        objects_fetched = len(poll.objects)

        with RawAlertArchive(archive_root) as archive:
            for obj in poll.objects:
                archive.append(
                    alert={
                        "alert_id": obj.object_id,
                        "object": obj.raw,
                        "_source_topic": "lasair-lsst-rest/objects",
                    },
                    broker_flags={
                        "annotations": obj.annotations,
                        "n_candidates": obj.n_candidates,
                    },
                    ingest_time=datetime.now(timezone.utc),
                )

        detection_rows = _object_poll_to_detections(poll, lasair)

    detections_ingested, fresh_det_ids = _write_detections(db_path, detection_rows)

    # 4. Tracklet formation ---------------------------------------------
    # Lasair's `objects` rows are already pre-linked tracklets — Rubin's
    # upstream SSP pipeline associated these detections. Running
    # heliolinc3d on top of per-band aggregate rows is a noop at best
    # and a noise source at worst. So for the Lasair REST bridge we
    # group the synthesised detection rows by object_id directly and
    # call each group a tracklet.
    #
    # When a future Fink-Kafka ingest path lands (ADR-0013 migration)
    # it will deliver raw un-linked detections, and this pipeline will
    # switch back to heliolinc3d for that case.
    linker = HelioLinC3DRunner()  # kept so is_mock reflects binary presence
    detections_df = _fresh_detections_df(db_path, fresh_det_ids)
    tracklets: list[Tracklet] = _tracklets_from_lasair_objects(
        detections_df, db_path
    )
    tracklets_linked = len(tracklets)

    # Write tracklets and capture a DB id per tracklet
    tracklet_db_ids = _write_tracklets(db_path, tracklets)

    # 5. Orbit fit per tracklet ------------------------------------------
    # Honesty gate: when all detections in a tracklet share one sky
    # position (Lasair REST aggregate case) there is no astrometric arc
    # to fit and any "fit" would be fabricated. Mark those tracklets as
    # UNDETERMINED instead of producing mock-noise orbits that leak into
    # the watch list as false positives.
    fitter = FindOrbRunner()
    mock_mode_orbit = fitter.is_mock
    mock_mode_linking = linker.is_mock

    fits_by_tracklet: dict[str, tuple[int, OrbitFit]] = {}
    fits_ok = 0
    fits_failed = 0
    fits_undetermined = 0
    for trk in tracklets:
        try:
            use_iso = trk.mean_motion_arcsec_hr > 600.0
            dets = detections_df[
                detections_df["detection_id"].isin(trk.detection_ids)
            ][["detection_id", "mjd", "ra_deg", "dec_deg", "mag", "filter"]]
            if len(dets) < 2:
                fits_failed += 1
                continue

            # Degeneracy check: astrometric arc must have real sky
            # motion. If every detection sits inside a 0.5 arcsec radius
            # the tracklet is effectively a single point — skip.
            if _is_degenerate_arc(dets):
                fits_undetermined += 1
                continue

            fit = fitter.fit_tracklet(dets, use_interstellar=use_iso)
            orbit_fit_id = _write_orbit_fit(
                db_path, tracklet_db_ids[trk.tracklet_id], trk, fit
            )
            fits_by_tracklet[trk.tracklet_id] = (orbit_fit_id, fit)
            fits_ok += 1
        except Exception as exc:
            logger.warning("orbit fit failed for %s: %s", trk.tracklet_id, exc)
            fits_failed += 1

    # 6. Score + gate each tracklet --------------------------------------
    threshold_version_id = _latest_threshold_version_id(db_path)
    wl_counts = {"new": 0, "defer": 0, "reject": 0}
    for trk in tracklets:
        pair = fits_by_tracklet.get(trk.tracklet_id)
        if pair is None:
            continue
        orbit_fit_id, fit = pair
        category, status, null_tests, mpc_note = _gate(trk, fit, thresholds)
        if status not in {"new", "defer"}:
            wl_counts["reject"] += 1
            continue  # ADR-0005: only watch-list statuses are persisted
        _insert_watch_list(
            db_path,
            tracklet_db_id=tracklet_db_ids[trk.tracklet_id],
            orbit_fit_id=orbit_fit_id,
            category=category,
            status=status,
            null_tests=null_tests,
            mpc_note=mpc_note,
            threshold_version_id=threshold_version_id,
        )
        wl_counts[status] += 1

    # 7. Pipeline-health row for tonight ---------------------------------
    obs_night = _utc_night_label()
    ingest_label = "fink" if ingest_mode == "fink" else "lasair"
    _upsert_pipeline_health(
        db_path,
        obs_night=obs_night,
        alerts_ingested=objects_fetched,
        sso_candidates=objects_fetched,
        tracklets_linked=tracklets_linked,
        orbit_fits_ok=fits_ok,
        orbit_fits_failed=fits_failed + fits_undetermined,
        dropped_alerts=0,
        ingest_lag_s_p95=0.0,
        notes=(
            f"ingest={ingest_label} status={poll_http_status}; "
            f"linking={'mock' if mock_mode_linking else 'heliolinc3d'}, "
            f"fit={'mock' if mock_mode_orbit else 'find_orb'}, "
            f"undetermined={fits_undetermined} "
            f"({'aggregate-only arcs — needs per-detection source' if ingest_mode == 'lasair' else 'arc too short or coplanar'})"
        ),
    )

    return PipelineRunStats(
        poll_http_status=poll_http_status,
        objects_fetched=objects_fetched,
        detections_ingested=detections_ingested,
        tracklets_linked=tracklets_linked,
        orbit_fits_ok=fits_ok,
        orbit_fits_failed=fits_failed + fits_undetermined,
        watch_list_new=wl_counts["new"],
        watch_list_deferred=wl_counts["defer"],
        watch_list_rejected=wl_counts["reject"],
        mock_mode_orbit=mock_mode_orbit,
        mock_mode_linking=mock_mode_linking,
        obs_night=obs_night,
        notes=(
            f"undetermined={fits_undetermined} of {tracklets_linked} "
            "tracklets had no astrometric arc (aggregate-only input)."
            if fits_undetermined else ""
        ),
    )


# ---------------------------------------------------------------------------
# Ingest → detection normalisation
# ---------------------------------------------------------------------------


_LSST_BANDS = ("u", "g", "r", "i", "z", "y")


def _object_poll_to_detections(
    poll: LasairPoll, lasair: LasairRestConsumer
) -> list[dict[str, Any]]:
    """Expand Lasair aggregate-object rows into per-band detection rows.

    Lasair-LSST's `/api/query/` only exposes the aggregate `objects`
    table (ADR-0013) — per-detection astrometry is not available over
    REST. We compensate by treating the per-band ``{band}_latestMJD`` +
    ``{band}_psfFlux*`` columns as separate detection points, sharing
    the object's aggregate ``(ra, decl)``. This yields up to 6 rows per
    object.

    Limitations (known and deliberate):
    - All synthesised rows share one coordinate, so the mock linker
      produces zero-motion tracklets. Orbit-fit output in this mode is
      therefore placeholder-noise even more aggressively than usual.
    - For real astrometry-based scoring the ingest path must be
      migrated to Fink Kafka. See ADR-0013 "Migration path" section.
    """
    out: list[dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for obj in poll.objects:
        ra = obj.ra_deg
        dec = obj.dec_deg
        if not (math.isfinite(ra) and math.isfinite(dec)):
            continue
        bucket = healpix_index.bucket(float(ra), float(dec))
        for band in _LSST_BANDS:
            mjd = _pick_float(obj.raw, (f"{band}_latestMJD",))
            if mjd is None:
                continue
            psf_flux = _pick_float(obj.raw, (f"{band}_psfFlux", f"{band}_psfFluxMean"))
            psf_flux_err = _pick_float(obj.raw, (f"{band}_psfFluxMeanErr", f"{band}_psfFluxSigma"))
            alert_id = f"{obj.object_id}:{band}"
            out.append(
                {
                    "alert_id": alert_id,
                    "object_id": obj.object_id,
                    "ra": float(ra),
                    "dec": float(dec),
                    "mjd": float(mjd),
                    "band": band,
                    "psf_flux": psf_flux,
                    "psf_flux_err": psf_flux_err,
                    "snr": _compute_snr(psf_flux, psf_flux_err),
                    "reliability": obj.reliability,
                    "streak_flag": 0,
                    "healpix_bucket": bucket,
                    "ingest_time_utc": now_iso,
                }
            )
        # If no per-band MJDs exist at all, synthesise bookend rows from
        # firstDiaSourceMjdTai / lastDiaSourceMjdTai so the tracklet
        # linker has ≥ 2 points to work with.
        if not any(f"{b}_latestMJD" in obj.raw and obj.raw[f"{b}_latestMJD"] for b in _LSST_BANDS):
            for idx, mjd in enumerate([obj.mjd_min, obj.mjd_max]):
                if not mjd:
                    continue
                out.append(
                    {
                        "alert_id": f"{obj.object_id}:agg{idx}",
                        "object_id": obj.object_id,
                        "ra": float(ra),
                        "dec": float(dec),
                        "mjd": float(mjd),
                        "band": "r",
                        "psf_flux": None,
                        "psf_flux_err": None,
                        "snr": None,
                        "reliability": obj.reliability,
                        "streak_flag": 0,
                        "healpix_bucket": bucket,
                        "ingest_time_utc": now_iso,
                    }
                )
    return out


def _write_detections(
    db_path: Path, rows: list[dict[str, Any]]
) -> tuple[int, list[int]]:
    """Insert fresh detection rows. Returns (count, detection_ids_inserted)."""
    if not rows:
        return 0, []
    with schema.connect(db_path) as conn:
        existing = {
            r[0]
            for r in conn.execute(
                f"SELECT alert_id FROM detections WHERE alert_id IN "
                f"({','.join(['?']*len(rows))})",
                [r["alert_id"] for r in rows],
            ).fetchall()
        }
        fresh = [r for r in rows if r["alert_id"] not in existing]
        if not fresh:
            return 0, []
        conn.executemany(
            """
            INSERT INTO detections
                (alert_id, ra, dec, mjd, band, psf_flux, psf_flux_err,
                 snr, reliability, streak_flag, healpix_bucket, ingest_time_utc)
            VALUES (:alert_id, :ra, :dec, :mjd, :band, :psf_flux, :psf_flux_err,
                    :snr, :reliability, :streak_flag, :healpix_bucket, :ingest_time_utc)
            """,
            fresh,
        )
        conn.commit()
        fresh_ids = [
            r[0]
            for r in conn.execute(
                f"SELECT detection_id FROM detections WHERE alert_id IN "
                f"({','.join(['?']*len(fresh))})",
                [r["alert_id"] for r in fresh],
            ).fetchall()
        ]
        return len(fresh), fresh_ids


# ---------------------------------------------------------------------------
# Linker input prep
# ---------------------------------------------------------------------------


def _is_degenerate_arc(dets: pd.DataFrame, max_spread_arcsec: float = 0.5) -> bool:
    """True when every detection sits inside a tiny cone — no real motion.

    Lasair REST's aggregate objects table gives one ``(ra, decl)`` per
    object, replicated across per-band rows. Fitting an orbit to those
    replicated points produces noise dressed up as physics. This check
    treats such tracklets as having an insufficient astrometric arc; the
    pipeline marks them ``undetermined`` and they do not enter the
    watch list. When a real per-detection source (Fink Kafka) comes
    online this check becomes a no-op for non-degenerate inputs.
    """
    if len(dets) < 2:
        return False
    import numpy as _np
    ra = dets["ra_deg"].to_numpy(dtype=float)
    dec = dets["dec_deg"].to_numpy(dtype=float)
    mean_dec = float(_np.deg2rad(_np.mean(dec)))
    dra = (ra - ra[0]) * _np.cos(mean_dec)
    ddec = dec - dec[0]
    sep_arcsec = _np.hypot(dra, ddec) * 3600.0
    return bool(_np.max(sep_arcsec) <= max_spread_arcsec)


def _tracklets_from_lasair_objects(
    detections_df: pd.DataFrame, db_path: Path
) -> list[Tracklet]:
    """Build one Tracklet per Lasair object (Lasair rows are pre-linked).

    Groups rows by object_id. The object_id is encoded in the alert_id
    as ``{object_id}:{band_or_agg}`` (see ``_object_poll_to_detections``),
    so we parse it back out rather than re-joining against a source map.
    """
    if detections_df.empty:
        return []

    # Pull alert_id alongside each detection so we can recover object_id.
    with schema.connect(db_path) as conn:
        ids = [int(x) for x in detections_df["detection_id"].tolist()]
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT detection_id, alert_id FROM detections "
            f"WHERE detection_id IN ({placeholders})",
            ids,
        ).fetchall()
    alert_by_det = {r[0]: r[1] for r in rows}

    def _obj_from_alert(alert: str) -> str:
        # alert_id shape: "{object_id}:{suffix}"
        return alert.rsplit(":", 1)[0] if ":" in alert else alert

    detections_df = detections_df.assign(
        alert_id=detections_df["detection_id"].map(alert_by_det).astype(str),
    )
    detections_df = detections_df.assign(
        object_id=detections_df["alert_id"].map(_obj_from_alert).astype(str),
    )
    detections_df = detections_df[detections_df["object_id"] != ""]

    tracklets: list[Tracklet] = []
    for obj_id, chunk in detections_df.groupby("object_id"):
        if len(chunk) < 2:
            # Orbit fit needs ≥2 points; skip singleton-band objects.
            continue
        mjd = chunk["mjd"].to_numpy()
        arc_days = float(mjd.max() - mjd.min())
        n_nights = int(max(1, round(arc_days))) if arc_days > 0 else 1
        tracklets.append(
            Tracklet(
                tracklet_id=f"lasair-{obj_id}",
                detection_ids=[int(d) for d in chunk["detection_id"].tolist()],
                n_detections=int(len(chunk)),
                n_nights=n_nights,
                mjd_start=float(mjd.min()),
                mjd_end=float(mjd.max()),
                mean_ra_deg=float(chunk["ra_deg"].mean()),
                mean_dec_deg=float(chunk["dec_deg"].mean()),
                mean_motion_arcsec_hr=0.0,  # Lasair-aggregate → zero intra-object motion
                quality_flag="ok",
                source="lasair-aggregate",
            )
        )
    return tracklets


def _fresh_detections_df(db_path: Path, ids: list[int]) -> pd.DataFrame:
    """Return a DataFrame of just the detection rows inserted this run.

    Scoped to the fresh IDs so re-running the pipeline does not re-link
    old tracklets into new ones. heliolinc3d expects ``ra_deg``,
    ``dec_deg`` column names so we alias here.
    """
    if not ids:
        return pd.DataFrame(
            columns=["detection_id", "mjd", "ra_deg", "dec_deg", "mag", "filter"]
        )
    with schema.connect(db_path) as conn:
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT detection_id, mjd, ra AS ra_deg, dec AS dec_deg, "
            f"       psf_flux AS mag, band AS filter "
            f"FROM detections WHERE detection_id IN ({placeholders}) "
            f"ORDER BY mjd ASC",
            ids,
        ).fetchall()
    if not rows:
        return pd.DataFrame(
            columns=["detection_id", "mjd", "ra_deg", "dec_deg", "mag", "filter"]
        )
    return pd.DataFrame([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Persistence helpers (tracklets, orbit_fits, watch_list, health)
# ---------------------------------------------------------------------------


def _write_tracklets(
    db_path: Path, tracklets: list[Tracklet]
) -> dict[str, int]:
    """Insert tracklets into the DB, return {linker_id: db_row_id}."""
    ids: dict[str, int] = {}
    if not tracklets:
        return ids
    with schema.connect(db_path) as conn:
        for trk in tracklets:
            cur = conn.execute(
                """
                INSERT INTO tracklets
                    (detection_ids_json, num_nights, total_arc_hours, created_utc)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (
                    json.dumps(trk.detection_ids),
                    int(trk.n_nights),
                    float((trk.mjd_end - trk.mjd_start) * 24.0),
                ),
            )
            ids[trk.tracklet_id] = int(cur.lastrowid)
        conn.commit()
    return ids


def _write_orbit_fit(
    db_path: Path, tracklet_db_id: int, trk: Tracklet, fit: OrbitFit
) -> int:
    software_version = (
        fit.software_version if fit.mode != "mock" else "mock-findorb-0"
    )
    with schema.connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO orbit_fits
                (tracklet_id, a_au, e, incl_deg, perihelion_au, aphelion_au,
                 A1, A2, A3, sigma_e, sigma_A1, sigma_A2, sigma_A3,
                 fit_rms, n_obs, software_version, fit_time_utc)
            VALUES (?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, datetime('now'))
            """,
            (
                tracklet_db_id,
                _nan_to_none(fit.a),
                _nan_to_none(fit.e),
                _nan_to_none(fit.i),
                _nan_to_none(fit.q),
                _nan_to_none(fit.Q),
                _nan_to_none(fit.A1),
                _nan_to_none(fit.A2),
                _nan_to_none(fit.A3),
                _nan_to_none(fit.sigma_e),
                _nan_to_none(fit.sigma_A1),
                _nan_to_none(fit.sigma_A2),
                _nan_to_none(fit.sigma_A3),
                _nan_to_none(fit.fit_rms),
                int(fit.n_obs),
                software_version,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def _insert_watch_list(
    db_path: Path,
    *,
    tracklet_db_id: int,
    orbit_fit_id: int,
    category: str,
    status: str,
    null_tests: dict[str, Any],
    mpc_note: str | None,
    threshold_version_id: int | None,
) -> int:
    # ADR-0005: never persist 'promoted' or 'accept' here.
    if status in {"promoted", "accept"}:
        raise RuntimeError(
            f"ADR-0005 violation: pipeline attempted status={status!r}"
        )
    tests_json = json.dumps(
        {k: _null_test_to_ui(v) for k, v in null_tests.items()},
    )
    with schema.connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO watch_list
                (category, tracklet_id, orbit_fit_id, created_utc, status,
                 null_test_results_json, mpc_crossmatch, notes,
                 threshold_version_id)
            VALUES (?, ?, ?, datetime('now'), ?, ?, ?, NULL, ?)
            """,
            (
                category,
                tracklet_db_id,
                orbit_fit_id,
                status,
                tests_json,
                mpc_note,
                threshold_version_id,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def _upsert_pipeline_health(
    db_path: Path,
    *,
    obs_night: str,
    alerts_ingested: int,
    sso_candidates: int,
    tracklets_linked: int,
    orbit_fits_ok: int,
    orbit_fits_failed: int,
    dropped_alerts: int,
    ingest_lag_s_p95: float,
    notes: str,
) -> None:
    with schema.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO pipeline_health
                (obs_night, alerts_ingested, sso_candidates, tracklets_linked,
                 orbit_fits_ok, orbit_fits_failed, dropped_alerts,
                 ingest_lag_s_p95, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(obs_night) DO UPDATE SET
                alerts_ingested   = excluded.alerts_ingested,
                sso_candidates    = excluded.sso_candidates,
                tracklets_linked  = excluded.tracklets_linked,
                orbit_fits_ok     = excluded.orbit_fits_ok,
                orbit_fits_failed = excluded.orbit_fits_failed,
                dropped_alerts    = excluded.dropped_alerts,
                ingest_lag_s_p95  = excluded.ingest_lag_s_p95,
                notes             = excluded.notes
            """,
            (
                obs_night,
                alerts_ingested,
                sso_candidates,
                tracklets_linked,
                orbit_fits_ok,
                orbit_fits_failed,
                dropped_alerts,
                ingest_lag_s_p95,
                notes,
            ),
        )
        conn.commit()


def _ensure_threshold_version_row(db_path: Path, thresholds: Thresholds) -> None:
    commit = _git_commit_short()
    tag = f"thresholds-{thresholds.schema_version}"
    with schema.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO threshold_versions
                (config_tag, git_commit, locked, first_seen_utc)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (tag, commit, int(thresholds.locked)),
        )
        conn.commit()


def _latest_threshold_version_id(db_path: Path) -> int | None:
    with schema.connect(db_path) as conn:
        row = conn.execute(
            "SELECT version_id FROM threshold_versions "
            "ORDER BY version_id DESC LIMIT 1"
        ).fetchone()
    return int(row[0]) if row else None


# ---------------------------------------------------------------------------
# Gate bridge — run scoring + null tests, map to schema.py statuses
# ---------------------------------------------------------------------------


def _gate(
    trk: Tracklet, fit: OrbitFit, thresholds: Thresholds
) -> tuple[str, str, dict[str, Any], str | None]:
    """Return (category, status, null_tests, mpc_note) per ADR-0005.

    status is always one of: ``new`` | ``defer`` | ``reject``.
    ``accept`` and ``promoted`` are never assigned here.
    """
    morphology: dict[str, Any] = {}  # morphology table not yet populated
    dc = score_dark_comet(fit, morphology, thresholds.dark_comet)
    iso = score_iso(fit, thresholds.iso)
    null_tests = run_null_tests(trk, fit, morphology)

    # Common gate — did the tracklet survive basic arc/detection quality?
    c = thresholds.common
    common_ok = (
        trk.n_detections >= c.min_detections_per_tracklet
        and trk.n_nights >= c.min_nights_spanned
    )

    null_reject = [
        t for t in null_tests.values() if not t.passed and t.severity == "reject"
    ]
    null_warn = [
        t for t in null_tests.values() if not t.passed and t.severity == "warn"
    ]

    if not common_ok or null_reject:
        return "dark_comet", "reject", null_tests, None

    if null_warn:
        # Deferred — ambiguous, review after more data
        category = "iso" if iso.passes and not iso.refused else "dark_comet"
        return category, "defer", null_tests, None

    if iso.passes and not iso.refused:
        return "iso", "new", null_tests, None
    if dc.passes:
        return "dark_comet", "new", null_tests, None
    return "dark_comet", "reject", null_tests, None


def _null_test_to_ui(nt: Any) -> str:
    """Flatten null-test dataclass for dashboard consumption."""
    sev = getattr(nt, "severity", "info")
    detail = getattr(nt, "detail", "")
    passed = getattr(nt, "passed", True)
    head = "pass" if passed else ("warn" if sev == "warn" else "fail")
    if detail:
        return f"{head} — {detail}"
    return head


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------


def _now_mjd() -> float:
    # MJD at Unix epoch 1970-01-01T00:00:00Z = 40587.0
    now_utc = datetime.now(timezone.utc)
    return 40587.0 + now_utc.timestamp() / 86400.0


def _utc_night_label() -> str:
    # Rubin observing nights roll over at UTC — good enough for a personal tool.
    return date.today().isoformat()


def _pick_float(d: dict, keys: tuple[str, ...]) -> float | None:
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            return f
    return None


def _compute_snr(flux: float | None, err: float | None) -> float | None:
    if flux is None or err in (None, 0) or err == 0.0:
        return None
    try:
        return float(flux) / float(err)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _nan_to_none(v: float | None) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _git_commit_short() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(_PROJECT_ROOT), "rev-parse", "--short", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip() or "unknown"
    except Exception:
        pass
    return "unknown"
