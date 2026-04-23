"""SQLite query helpers for the dashboard.

Talks to the detection DB produced by src/rubin_hunter/detection_db and populated
in demo mode by scripts/make_demo_db.py. All queries are read-only; writes happen
only via dashboard.lib.decisions when a user takes a decision action.

See ADR-0009 (own history layer), PRD §F10 (append-only decision audit).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import streamlit as st


DEMO_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "demo.sqlite"


@st.cache_resource(show_spinner=False)
def get_connection(db_path: str | Path = DEMO_DB_PATH) -> sqlite3.Connection:
    """Cached read-only-ish SQLite connection. Row factory returns sqlite3.Row."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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
