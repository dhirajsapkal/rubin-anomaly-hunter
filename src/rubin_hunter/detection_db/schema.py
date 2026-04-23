"""SQLite schema for the own detection-history DB (per ADR-0009).

ADR-0009 says we cannot depend on broker-supplied ``prv_diaSources`` — in
early LSST operations those arrive sparse or empty for Solar System
objects, and broker cross-match flags drift silently. So we accumulate
our own copy of every SSO-candidate detection and run linking +
orbit-fitting against this local DB.

Tables
------
``detections``
    One row per DIA source we have ever ingested. Bucketed by HEALPix
    for O(log N) cone-search queries.

``tracklets``
    Linked sets of detections produced by ``heliolinc3d`` (ADR-0007).
    ``detection_ids`` is a JSON array — SQLite has no arrays but this
    column is only ever read through Python, never queried with SQL
    array ops.

``orbit_fits``
    One row per ``find_orb`` fit (ADR-0008). Includes Marsden A1, A2,
    A3 non-gravitational terms and their sigmas because dark-comet
    detection is exactly these residuals (PRD §5).

``watch_list``
    Stage A entries per the two-stage gate (ADR-0005). Category is
    strictly ``dark_comet`` or ``iso``. Status transitions happen only
    via rows in ``decisions``.

``decisions``
    Append-only audit log. PRD §11 and success metric "audit log
    captures 100% of decisions" depend on this being append-only —
    never update or delete rows, only insert.

``threshold_versions``
    Which config tag + commit hash was in force when each entry was
    created or evaluated. Needed by ADR-0006 (threshold lock is dated
    and git-tagged): the question "what thresholds were this entry
    judged against?" must have an unambiguous answer.

Connection pragmas
------------------
* ``journal_mode=WAL`` — concurrent reader while ingest writes.
* ``foreign_keys=ON`` — FK constraints are not enforced in SQLite by
  default; turn them on.
* ``synchronous=NORMAL`` — WAL-safe, faster than ``FULL``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS detections (
    detection_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id           TEXT    NOT NULL,
    ra                 REAL    NOT NULL,
    dec                REAL    NOT NULL,
    mjd                REAL    NOT NULL,
    band               TEXT    NOT NULL,
    psf_flux           REAL,
    psf_flux_err       REAL,
    snr                REAL,
    reliability        REAL,
    streak_flag        INTEGER NOT NULL DEFAULT 0,
    healpix_bucket     INTEGER NOT NULL,
    ingest_time_utc    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_detections_healpix ON detections(healpix_bucket);
CREATE INDEX IF NOT EXISTS idx_detections_mjd     ON detections(mjd);
CREATE INDEX IF NOT EXISTS idx_detections_alert   ON detections(alert_id);

CREATE TABLE IF NOT EXISTS tracklets (
    tracklet_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    detection_ids_json TEXT    NOT NULL,
    num_nights         INTEGER NOT NULL,
    total_arc_hours    REAL    NOT NULL,
    created_utc        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS orbit_fits (
    orbit_fit_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    tracklet_id        INTEGER NOT NULL,
    -- NB: SQLite identifiers are case-insensitive, so we cannot use
    -- the astronomy-standard "q" and "Q" as separate columns. Stored
    -- as perihelion_au / aphelion_au; symbolic names appear in the UI.
    a_au               REAL,
    e                  REAL,
    incl_deg           REAL,
    perihelion_au      REAL,
    aphelion_au        REAL,
    A1                 REAL,
    A2                 REAL,
    A3                 REAL,
    sigma_e            REAL,
    sigma_A1           REAL,
    sigma_A2           REAL,
    sigma_A3           REAL,
    fit_rms            REAL,
    n_obs              INTEGER NOT NULL,
    software_version   TEXT    NOT NULL,
    fit_time_utc       TEXT    NOT NULL,
    FOREIGN KEY(tracklet_id) REFERENCES tracklets(tracklet_id)
);
CREATE INDEX IF NOT EXISTS idx_orbit_fits_tracklet ON orbit_fits(tracklet_id);

CREATE TABLE IF NOT EXISTS watch_list (
    entry_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category           TEXT    NOT NULL CHECK (category IN ('dark_comet','iso')),
    tracklet_id        INTEGER NOT NULL,
    orbit_fit_id       INTEGER NOT NULL,
    created_utc        TEXT    NOT NULL,
    status             TEXT    NOT NULL CHECK (status IN ('new','defer','reject','accept','promoted')),
    null_test_results_json TEXT NOT NULL,
    mpc_crossmatch     TEXT,
    notes              TEXT,
    threshold_version_id INTEGER,
    FOREIGN KEY(tracklet_id)  REFERENCES tracklets(tracklet_id),
    FOREIGN KEY(orbit_fit_id) REFERENCES orbit_fits(orbit_fit_id),
    FOREIGN KEY(threshold_version_id) REFERENCES threshold_versions(version_id)
);
CREATE INDEX IF NOT EXISTS idx_watch_list_status   ON watch_list(status);
CREATE INDEX IF NOT EXISTS idx_watch_list_category ON watch_list(category);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id           INTEGER NOT NULL,
    decision           TEXT    NOT NULL CHECK (decision IN ('accept','defer','reject','promote')),
    note               TEXT,
    decided_utc        TEXT    NOT NULL,
    FOREIGN KEY(entry_id) REFERENCES watch_list(entry_id)
);
CREATE INDEX IF NOT EXISTS idx_decisions_entry ON decisions(entry_id);

CREATE TABLE IF NOT EXISTS threshold_versions (
    version_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    config_tag         TEXT    NOT NULL,
    git_commit         TEXT    NOT NULL,
    locked             INTEGER NOT NULL DEFAULT 0,
    first_seen_utc     TEXT    NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_threshold_versions_tag_commit
    ON threshold_versions(config_tag, git_commit);

CREATE TABLE IF NOT EXISTS pipeline_health (
    health_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    obs_night          TEXT    NOT NULL,
    alerts_ingested    INTEGER NOT NULL,
    sso_candidates     INTEGER NOT NULL,
    tracklets_linked   INTEGER NOT NULL,
    orbit_fits_ok      INTEGER NOT NULL,
    orbit_fits_failed  INTEGER NOT NULL,
    dropped_alerts     INTEGER NOT NULL,
    ingest_lag_s_p95   REAL    NOT NULL,
    notes              TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pipeline_health_night
    ON pipeline_health(obs_night);
"""


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")


def init_db(db_path: Path) -> None:
    """Create schema idempotently at ``db_path``.

    Safe to call against an existing DB — every ``CREATE`` is gated with
    ``IF NOT EXISTS``. Per ADR-0009 this file is load-bearing; callers
    should back it up alongside the raw alert archive.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        _apply_pragmas(conn)
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with project-standard pragmas applied.

    Also sets ``row_factory = sqlite3.Row`` so callers can index columns
    by name. WAL + ``foreign_keys=ON`` apply per-connection in SQLite;
    every caller must go through this helper, not a bare
    ``sqlite3.connect``.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _apply_pragmas(conn)
    return conn
