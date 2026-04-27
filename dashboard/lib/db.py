"""SQLite query helpers for the dashboard.

Talks to the detection DB produced by src/rubin_hunter/detection_db and populated
in demo mode by scripts/make_demo_db.py. All queries are read-only; writes happen
only via dashboard.lib.decisions when a user takes a decision action.

See ADR-0009 (own history layer), PRD §F10 (append-only decision audit).
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import streamlit as st

from .rehydrate import RehydrateResult, ensure_live_db


_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEMO_DB_PATH = _DATA_DIR / "demo.sqlite"
LIVE_DB_PATH = _DATA_DIR / "live.sqlite"


@st.cache_resource(show_spinner="Fetching latest pipeline state…", ttl=300)
def _rehydrate_once() -> RehydrateResult:
    """Pull live.sqlite from the data branch — re-fetched every 5 minutes.

    No-op when ``RUBIN_HUNTER_REHYDRATE_URL`` isn't set (local dev). On
    Streamlit Community Cloud, configure that env var to the raw URL of
    ``data/live.sqlite`` on the orphan ``data`` branch — see ADR-0017.

    Caching policy: ``ttl=300`` (5 minutes). Without a TTL, a Streamlit
    Cloud container that boots before the pipeline first publishes data
    will cache an empty/error result and serve it until the container
    recycles (~24 h). The pipeline runs every 4 h, so 5 min × at-most-48
    re-fetches per cron tick is the right cost/freshness trade — and the
    underlying ``If-Modified-Since`` header makes the no-change case a
    cheap 304.

    A pure failure (``source == "error"`` with no existing local DB)
    raises, which ``st.cache_resource`` does not cache — so the next
    page load retries.
    """
    result = ensure_live_db(LIVE_DB_PATH)
    if result.source == "error" and not LIVE_DB_PATH.exists():
        raise RuntimeError(f"rehydrate failed: {result.error}")
    if result.source == "remote-fresh":
        # We just replaced live.sqlite on disk via atomic rename. Any
        # SQLite connection cached by `get_connection` is still pointing
        # at the old inode (the OS keeps it alive until close), so the
        # dashboard would keep reading the previous DB until the
        # connection cache turns over. Clear it now so the next query
        # opens a fresh connection against the new file.
        get_connection.clear()
    return result


def rehydrate_status() -> RehydrateResult:
    """Public accessor so Health/footer can show fetch provenance."""
    try:
        return _rehydrate_once()
    except Exception as exc:  # noqa: BLE001 — we want to surface, not crash
        return RehydrateResult(
            source="error",
            url=None,
            dest=LIVE_DB_PATH,
            bytes_written=0,
            error=str(exc),
            fetched_at_utc=0.0,
        )


def resolve_db_path() -> Path:
    """Decide which SQLite file the dashboard reads from.

    Resolution order:
      1. ``RUBIN_HUNTER_DB`` env var, if it points at a readable file.
      2. Trigger a rehydrate-from-data-branch (ADR-0017) — no-op if the
         remote-URL env var isn't set. May materialise ``data/live.sqlite``
         on Streamlit Cloud cold-start.
      3. ``data/live.sqlite`` if it exists AND holds any evidence of a real
         pipeline run (detections ingested, tracklets linked, pipeline_health
         logged). Empty-watch-list is fine — the honesty gate correctly
         rejects degenerate aggregate-only arcs; the dashboard should show
         that truth, not a synthetic demo.
      4. ``data/demo.sqlite`` only when live has never run.

    Live wins as soon as it reflects a real ingest. Demo remains the
    first-boot fallback so a fresh clone of the repo isn't empty.
    """
    env = os.environ.get("RUBIN_HUNTER_DB")
    if env:
        p = Path(env)
        if p.exists():
            return p
    # Attempt to rehydrate live.sqlite from the data branch. If the fetch
    # fails (first-boot race, URL unset, network blip), don't crash — fall
    # through to the demo DB. The exception here is deliberately silenced
    # because _rehydrate_once() raises on failure precisely so the cache
    # doesn't stick; callers re-try on the next page render.
    try:
        _rehydrate_once()
    except Exception:  # noqa: BLE001 — rehydrate is best-effort
        pass
    if LIVE_DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(LIVE_DB_PATH))
            try:
                row = conn.execute(
                    "SELECT "
                    "  (SELECT COUNT(*) FROM detections) AS n_det, "
                    "  (SELECT COUNT(*) FROM pipeline_health) AS n_health"
                ).fetchone()
                has_run = bool(row and (row[0] > 0 or row[1] > 0))
            finally:
                conn.close()
            if has_run:
                return LIVE_DB_PATH
        except sqlite3.Error:
            pass
    return DEMO_DB_PATH


@st.cache_resource(show_spinner=False, ttl=120)
def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Cached SQLite connection. Defaults to :func:`resolve_db_path`.

    ``ttl=120`` ensures we open a new connection at least every 2 minutes
    — important on Streamlit Cloud where ``_rehydrate_once`` may replace
    ``live.sqlite`` underneath us (atomic rename leaves the prior inode
    intact for any open connection). Without the TTL, a long-lived
    container would keep reading the original file even after the data
    branch has been refreshed. ``_rehydrate_once`` also calls
    ``get_connection.clear()`` on every fresh fetch for an immediate
    invalidation, but the TTL is the safety net.
    """
    p = Path(db_path) if db_path is not None else resolve_db_path()
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def data_source_info(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return a dashboard-facing description of the active data source.

    Keys:
      db_path          — absolute path to the SQLite file
      is_live          — True when running against live.sqlite, False for demo
      any_mock_fit     — True if any orbit_fits row has a 'mock' software_version
      any_mock_linker  — True if any tracklet came from mock linking (reliably
                         inferable from pipeline_health.notes)
      last_run_notes   — the notes string from the most recent pipeline_health row
    """
    db_path = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    is_live = db_path.name == "live.sqlite"
    any_mock_fit = False
    any_mock_linker = False
    orbit_count = 0
    last_run_notes = ""
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM orbit_fits "
            "WHERE lower(software_version) LIKE '%mock%'"
        ).fetchone()
        any_mock_fit = bool(row and row[0] > 0)
        row = conn.execute("SELECT COUNT(*) FROM orbit_fits").fetchone()
        orbit_count = int(row[0]) if row else 0
        row = conn.execute(
            "SELECT notes FROM pipeline_health ORDER BY obs_night DESC LIMIT 1"
        ).fetchone()
        last_run_notes = (row["notes"] if row else "") or ""
        any_mock_linker = "linking=mock" in last_run_notes
    except sqlite3.Error:
        pass
    return {
        "db_path": str(db_path),
        "is_live": is_live,
        "any_mock_fit": any_mock_fit,
        "any_mock_linker": any_mock_linker,
        "orbit_count": orbit_count,
        "last_run_notes": last_run_notes,
    }


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


# ---- Tonight (home) summary ------------------------------------------------

def tonight_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Counts + delta for the Tonight home page.

    Returns a dict with: new_total, new_dark_comet, new_iso, alerts_ingested_last,
    tracklets_linked_last, last_night, promoted_recent, window_state, config_tag.
    """
    new_rows = conn.execute(
        "SELECT category, COUNT(*) AS n FROM watch_list "
        "WHERE status = 'new' GROUP BY category"
    ).fetchall()
    by_cat = {r["category"]: r["n"] for r in new_rows}

    last_health = conn.execute(
        "SELECT * FROM pipeline_health ORDER BY obs_night DESC LIMIT 1"
    ).fetchone()

    promoted_recent = conn.execute(
        "SELECT COUNT(*) AS n FROM watch_list WHERE status = 'promoted' "
        "AND created_utc >= datetime('now', '-14 days')"
    ).fetchone()["n"]

    thr = conn.execute(
        "SELECT config_tag, locked FROM threshold_versions "
        "ORDER BY version_id DESC LIMIT 1"
    ).fetchone()
    config_tag = thr["config_tag"] if thr else "unknown"
    window_state = "discovery" if (thr and thr["locked"]) else "commissioning"

    return {
        "new_total": sum(by_cat.values()),
        "new_dark_comet": by_cat.get("dark_comet", 0),
        "new_iso": by_cat.get("iso", 0),
        "alerts_ingested_last": last_health["alerts_ingested"] if last_health else 0,
        "tracklets_linked_last": last_health["tracklets_linked"] if last_health else 0,
        "last_night": last_health["obs_night"] if last_health else None,
        "promoted_recent": promoted_recent,
        "window_state": window_state,
        "config_tag": config_tag,
    }


def last_n_nights_health(conn: sqlite3.Connection, n: int = 14) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM pipeline_health ORDER BY obs_night DESC LIMIT ?", (n,)
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def nights_for_cadence(conn: sqlite3.Connection, n: int = 14) -> list[dict[str, Any]]:
    """Cadence-bar-ready health rows. Tags the most-recent row ``is_tonight``.

    Shape matches what `dashboard.lib.cadence.cadence_bar_svg` expects:
    ``{"obs_night": str, "tracklets": int, "alerts": int, "is_tonight": bool}``.
    """
    rows = last_n_nights_health(conn, n=n)
    if not rows:
        return []
    out = []
    last_idx = len(rows) - 1
    for i, r in enumerate(rows):
        out.append({
            "obs_night": r.get("obs_night") or "",
            "tracklets": int(r.get("tracklets_linked") or 0),
            "alerts":    int(r.get("alerts_ingested") or 0),
            "is_tonight": i == last_idx,
        })
    return out


def detections_for_skymap(
    conn: sqlite3.Connection,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Return recent detection rows shaped for `all_sky_svg`.

    Shape: ``{"ra_deg": float, "dec_deg": float, "band": str, "flagged": bool}``.
    A detection is ``flagged`` iff it belongs to a tracklet that landed in the
    watch_list with status ``new`` or ``defer`` (not yet resolved).
    """
    rows = conn.execute(
        """
        SELECT d.ra AS ra_deg, d.dec AS dec_deg, d.band,
               CASE
                 WHEN w.entry_id IS NOT NULL THEN 1
                 ELSE 0
               END AS flagged
        FROM detections d
        LEFT JOIN tracklets t
          ON t.detection_ids_json LIKE ('%' || d.detection_id || '%')
        LEFT JOIN watch_list w
          ON w.tracklet_id = t.tracklet_id
         AND w.status IN ('new','defer')
        ORDER BY d.mjd DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def tracklet_population_rails(
    conn: sqlite3.Connection, exclude_orbit_fit_id: int | None = None
) -> dict[str, list[float]]:
    """Tonight's population for e / |A1| / fit_rms strip-plots.

    Returns a dict of column → list of values across all orbit_fits recorded
    in the current DB, optionally excluding one entry (the one being viewed).
    Used by the Candidate canvas to show how a flagged entry sits against the
    population of other tracklets this pipeline saw.
    """
    q = "SELECT orbit_fit_id, e, A1, fit_rms FROM orbit_fits"
    rows = conn.execute(q).fetchall()
    out = {"e": [], "A1_abs": [], "fit_rms": []}
    for r in rows:
        if exclude_orbit_fit_id is not None and r["orbit_fit_id"] == exclude_orbit_fit_id:
            continue
        if r["e"] is not None:
            out["e"].append(float(r["e"]))
        if r["A1"] is not None:
            try:
                out["A1_abs"].append(abs(float(r["A1"])))
            except (TypeError, ValueError):
                pass
        if r["fit_rms"] is not None:
            out["fit_rms"].append(float(r["fit_rms"]))
    return out


# ---- Watch list ------------------------------------------------------------

def list_watch_list(
    conn: sqlite3.Connection,
    category: str | None = None,
    statuses: tuple[str, ...] = ("new", "defer"),
) -> list[dict[str, Any]]:
    q = (
        "SELECT w.entry_id, w.category, w.tracklet_id, w.orbit_fit_id, "
        "       w.created_utc, w.status, w.mpc_crossmatch, w.notes, "
        "       w.null_test_results_json, "
        "       t.num_nights, t.total_arc_hours, "
        "       o.a_au, o.e, o.incl_deg, o.perihelion_au, o.aphelion_au, "
        "       o.A1, o.A2, o.A3, o.sigma_e, o.n_obs, o.fit_rms "
        "FROM watch_list w "
        "LEFT JOIN tracklets t ON t.tracklet_id = w.tracklet_id "
        "LEFT JOIN orbit_fits o ON o.orbit_fit_id = w.orbit_fit_id "
    )
    clauses = []
    params: list[Any] = []
    if category:
        clauses.append("w.category = ?")
        params.append(category)
    if statuses:
        placeholders = ",".join("?" * len(statuses))
        clauses.append(f"w.status IN ({placeholders})")
        params.extend(statuses)
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY w.created_utc DESC"
    rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    # Parse null-test results so narrative.generate_why_flagged can use them
    for r in rows:
        raw = r.get("null_test_results_json") or "{}"
        try:
            r["null_tests"] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            r["null_tests"] = {}
    return rows


def get_watch_list_entry(conn: sqlite3.Connection, entry_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT w.*, t.num_nights, t.total_arc_hours, t.detection_ids_json, "
        "       o.a_au, o.e, o.incl_deg, o.perihelion_au, o.aphelion_au, "
        "       o.A1, o.A2, o.A3, o.sigma_e, o.sigma_A1, o.sigma_A2, o.sigma_A3, "
        "       o.fit_rms, o.n_obs, o.software_version, o.fit_time_utc, "
        "       tv.config_tag, tv.locked AS thresholds_locked "
        "FROM watch_list w "
        "LEFT JOIN tracklets t ON t.tracklet_id = w.tracklet_id "
        "LEFT JOIN orbit_fits o ON o.orbit_fit_id = w.orbit_fit_id "
        "LEFT JOIN threshold_versions tv ON tv.version_id = w.threshold_version_id "
        "WHERE w.entry_id = ?",
        (entry_id,),
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    try:
        d["null_tests"] = json.loads(d.get("null_test_results_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        d["null_tests"] = {}
    try:
        d["detection_ids"] = json.loads(d.get("detection_ids_json") or "[]")
    except (json.JSONDecodeError, TypeError):
        d["detection_ids"] = []
    return d


def get_detections(
    conn: sqlite3.Connection, detection_ids: list[int]
) -> list[dict[str, Any]]:
    if not detection_ids:
        return []
    placeholders = ",".join("?" * len(detection_ids))
    rows = conn.execute(
        f"SELECT * FROM detections WHERE detection_id IN ({placeholders}) "
        f"ORDER BY mjd ASC",
        detection_ids,
    ).fetchall()
    return [dict(r) for r in rows]


# ---- Decisions / archive ---------------------------------------------------

def list_decisions(
    conn: sqlite3.Connection,
    kind: str | None = None,
    decision: str | None = None,
) -> list[dict[str, Any]]:
    q = (
        "SELECT d.decision_id, d.entry_id, d.decision, d.note, d.decided_utc, "
        "       w.category, w.created_utc AS entry_created_utc, w.status "
        "FROM decisions d "
        "JOIN watch_list w ON w.entry_id = d.entry_id "
    )
    clauses = []
    params: list[Any] = []
    if kind:
        clauses.append("w.category = ?")
        params.append(kind)
    if decision:
        clauses.append("d.decision = ?")
        params.append(decision)
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY d.decided_utc DESC"
    return [dict(r) for r in conn.execute(q, params).fetchall()]


def entry_decisions(conn: sqlite3.Connection, entry_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM decisions WHERE entry_id = ? ORDER BY decided_utc ASC",
        (entry_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---- Writes (decision actions) --------------------------------------------

def append_decision(
    conn: sqlite3.Connection,
    entry_id: int,
    decision: str,
    note: str,
) -> int:
    """Append-only decision record. PRD §F10.

    Also updates the watch_list.status. Enforces ADR-0005: no direct write
    of status='promoted' except through this function called with decision='promote'.
    """
    if decision not in {"accept", "defer", "reject", "promote"}:
        raise ValueError(f"invalid decision: {decision!r}")
    # Status values match the schema CHECK constraint from src/rubin_hunter/
    # detection_db/schema.py (i.e. the demo generator schema): 'accept',
    # 'reject', 'defer', 'promoted'.
    terminal = {
        "accept": "accept",
        "reject": "reject",
        "promote": "promoted",
        "defer": "defer",
    }[decision]
    with conn:  # implicit transaction
        cur = conn.execute(
            "INSERT INTO decisions(entry_id, decision, note, decided_utc) "
            "VALUES(?, ?, ?, datetime('now'))",
            (entry_id, decision, note),
        )
        conn.execute(
            "UPDATE watch_list SET status = ? WHERE entry_id = ?",
            (terminal, entry_id),
        )
    return int(cur.lastrowid)
