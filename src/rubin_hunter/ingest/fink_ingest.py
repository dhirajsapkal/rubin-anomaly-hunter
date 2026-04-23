"""Fink Kafka → detection-row normaliser (ADR-0016).

Each LSST alert delivered by Fink carries the current ``diaSource`` plus an
array of ``prvDiaSources`` — the full multi-night detection history of
the object that triggered the alert. This module turns one alert into the
per-detection rows the rest of the pipeline wants.

Unlike the Lasair REST ingest (ADR-0013) which only exposes aggregate
per-object rows, Fink alerts give us the real (ra, dec, mjd) sequence,
which is what ``find_orb`` and ``heliolinc3d`` need to produce real
orbit fits and cross-night tracklets.

Shape of the returned dicts matches what ``pipeline._write_detections``
already expects::

    {
        "alert_id": str,          # diaSourceId as string
        "object_id": str,          # diaObjectId as string
        "ra": float,               # deg
        "dec": float,              # deg
        "mjd": float,              # midpointMjdTai
        "band": str,               # 'u'|'g'|'r'|'i'|'z'|'y'
        "psf_flux": float | None,
        "psf_flux_err": float | None,
        "snr": float | None,
        "reliability": float | None,
        "streak_flag": int,
        "healpix_bucket": int,     # added by caller via healpix_index.bucket
        "ingest_time_utc": str,
    }
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable

logger = logging.getLogger(__name__)


def _as_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def _band_name(b: Any) -> str:
    """Normalise band from alert payload. LSST uses integer fids in some
    schemas and string bands in others; accept both."""
    if b is None:
        return "r"
    if isinstance(b, (int, float)):
        # LSST passband integer code — map per alert schema.
        idx = int(b)
        return "ugrizy"[idx - 1] if 1 <= idx <= 6 else "r"
    s = str(b).strip().lower()
    return s[:1] if s else "r"


def _snr(flux: float | None, err: float | None) -> float | None:
    if flux is None or err in (None, 0) or err == 0.0:
        return None
    try:
        return float(flux) / float(err)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _diasource_to_detection(ds: dict, now_iso: str) -> dict[str, Any] | None:
    """Turn one diaSource dict into a detection row. Returns None if the
    source lacks the minimum (ra, dec, mjd) fields."""
    ra = _as_float(ds.get("ra"))
    dec = _as_float(ds.get("decl") if "decl" in ds else ds.get("dec"))
    mjd = _as_float(
        ds.get("midpointMjdTai") or ds.get("midpoint_mjd_tai")
        or ds.get("midpointmjd") or ds.get("mjd")
    )
    if ra is None or dec is None or mjd is None:
        return None

    dia_source_id = ds.get("diaSourceId") or ds.get("diasourceid") or ds.get("candid")
    dia_object_id = ds.get("diaObjectId") or ds.get("diaobjectid") or ds.get("objectId")
    if dia_source_id is None:
        # Synthesise a stable id from mjd + coords
        dia_source_id = f"{ra:.5f}:{dec:.5f}:{mjd:.5f}"

    flux = _as_float(ds.get("psfFlux") or ds.get("psflux"))
    err  = _as_float(ds.get("psfFluxErr") or ds.get("psfluxerr"))

    return {
        "alert_id": str(dia_source_id),
        "object_id": str(dia_object_id) if dia_object_id is not None else "unknown",
        "ra": ra,
        "dec": dec,
        "mjd": mjd,
        "band": _band_name(ds.get("band") or ds.get("filter") or ds.get("fid")),
        "psf_flux": flux,
        "psf_flux_err": err,
        "snr": _snr(flux, err),
        "reliability": _as_float(ds.get("reliability") or ds.get("drb") or ds.get("rb")),
        "streak_flag": int(bool(ds.get("streak_flag") or ds.get("isdiffpos_streak"))),
        "healpix_bucket": 0,   # caller fills this via healpix_index.bucket()
        "ingest_time_utc": now_iso,
    }


def alert_to_detections(alert: dict) -> list[dict[str, Any]]:
    """Expand one Fink LSST alert into its full detection history.

    Extracts:
      - ``alert["diaSource"]`` (the current detection that triggered the alert)
      - every row in ``alert["prvDiaSources"]`` (past detections of the
        same ``diaObjectId``)

    Deduplicates on ``diaSourceId``. Drops rows missing (ra, dec, mjd).
    """
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    def _push(ds: dict) -> None:
        row = _diasource_to_detection(ds, now_iso)
        if row is None:
            return
        if row["alert_id"] in seen:
            return
        seen.add(row["alert_id"])
        out.append(row)

    current = alert.get("diaSource") or alert.get("diasource")
    if isinstance(current, dict):
        _push(current)

    prv = alert.get("prvDiaSources") or alert.get("prv_dia_sources") or []
    if isinstance(prv, list):
        for ds in prv:
            if isinstance(ds, dict):
                _push(ds)

    return out


def broker_flags_from_alert(alert: dict) -> dict[str, Any]:
    """Snapshot cross-match flags verbatim at ingest time (ADR-0009).

    Never re-queried in place — a later re-check writes a new annotation,
    never mutates this snapshot. Keys that commonly appear on Fink LSST
    alerts: cdsxmatch, mpc_cross_match, sherlock, roid, mpchecker, etc.
    We pass all non-core keys through unchanged.
    """
    return {
        k: v
        for k, v in alert.items()
        if k not in {"diaSource", "diasource", "prvDiaSources", "prv_dia_sources",
                     "diaObject", "diaobject", "cutoutScience",
                     "cutoutTemplate", "cutoutDifference"}
    }


def batch_detections(alerts: Iterable[dict]) -> list[dict[str, Any]]:
    """Convenience — flatten detections across a batch of alerts."""
    out: list[dict[str, Any]] = []
    for alert in alerts:
        out.extend(alert_to_detections(alert))
    return out
