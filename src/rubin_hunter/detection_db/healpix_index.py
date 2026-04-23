"""HEALPix spatial bucketing for the detection DB (per ADR-0009 + PRD §6).

Motivation: a plain B-tree on (ra, dec) is disastrous for cone searches
near the poles and across the RA=0 wrap. HEALPix assigns every sky
position to an integer bucket at a chosen ``nside``; a cone query
degenerates to a precomputed list of overlapping buckets ``IN`` the
detection table's bucket column. PRD §6 calls for ``nside = 2^14`` —
~0.2 arcsec resolution — as the default for LSST-scale work; ADR-0009
allows this to be tuned during commissioning.

This module is intentionally tiny and pure: no SQLite writes happen
here, only reads. Writers compute the bucket with :func:`bucket` and
store it alongside each detection row.

Fallback: ``healpy`` is not installable on every Windows box (it needs a
C toolchain). If it fails to import we degrade gracefully to a coarse
plate-carrée grid — not astronomically correct near the poles, but it
keeps the demo and unit tests runnable. A warning is printed once.
"""

from __future__ import annotations

import math
import sqlite3
import warnings
from dataclasses import dataclass

try:
    import healpy as _hp  # type: ignore
    import numpy as _np
    _HEALPY_AVAILABLE = True
except Exception:  # pragma: no cover - depends on env
    _hp = None  # type: ignore
    _np = None  # type: ignore
    _HEALPY_AVAILABLE = False


DEFAULT_NSIDE = 16384  # 2^14 — per PRD §6
_WARNED = False


def _warn_fallback_once() -> None:
    global _WARNED
    if not _WARNED:
        warnings.warn(
            "healpy not available; using coarse plate-carrée fallback for "
            "HEALPix bucketing. Spatial queries will still work but are not "
            "astronomically correct near the poles.",
            stacklevel=3,
        )
        _WARNED = True


# ----------------------------------------------------------------------
# primitives
# ----------------------------------------------------------------------
def bucket(ra_deg: float, dec_deg: float, nside: int = DEFAULT_NSIDE) -> int:
    """Return the integer HEALPix bucket for ``(ra, dec)`` in NESTED scheme."""
    if _HEALPY_AVAILABLE:
        # HEALPix expects colatitude theta (radians from north pole) and
        # longitude phi (radians east of 0 RA).
        theta = math.radians(90.0 - dec_deg)
        phi = math.radians(ra_deg % 360.0)
        return int(_hp.ang2pix(nside, theta, phi, nest=True))  # type: ignore[union-attr]

    _warn_fallback_once()
    # Coarse fallback: tile RA into ``nside`` slices and Dec into
    # ``nside`` slices. Not equal-area but monotonic.
    ra_bin = int((ra_deg % 360.0) / 360.0 * nside)
    dec_bin = int((dec_deg + 90.0) / 180.0 * nside)
    return ra_bin * nside + dec_bin


def cone_buckets(
    ra_deg: float,
    dec_deg: float,
    radius_arcsec: float,
    nside: int = DEFAULT_NSIDE,
) -> list[int]:
    """Return the bucket ids touched by a cone of ``radius_arcsec``.

    The result is suitable for use with an SQLite ``IN`` clause. For
    small radii at ``nside=16384`` the list is typically 1–30 buckets.
    """
    radius_rad = math.radians(radius_arcsec / 3600.0)

    if _HEALPY_AVAILABLE:
        theta = math.radians(90.0 - dec_deg)
        phi = math.radians(ra_deg % 360.0)
        vec = _hp.ang2vec(theta, phi)  # type: ignore[union-attr]
        ids = _hp.query_disc(  # type: ignore[union-attr]
            nside, vec, radius_rad, inclusive=True, nest=True
        )
        return [int(x) for x in ids.tolist()]

    _warn_fallback_once()
    # Coarse fallback: enumerate tiled buckets that overlap the box
    # bounding the cone, padded by one cell on each side to avoid edge
    # misses from integer truncation. Accept some over-selection — the
    # SQL layer filters by exact great-circle distance downstream.
    ra_step = 360.0 / nside
    dec_step = 180.0 / nside
    radius_deg = radius_arcsec / 3600.0
    dec_lo = max(-90.0, dec_deg - radius_deg - dec_step)
    dec_hi = min(90.0, dec_deg + radius_deg + dec_step)
    cos_dec = max(1e-6, math.cos(math.radians(dec_deg)))
    ra_pad = radius_deg / cos_dec + ra_step
    ra_lo = (ra_deg - ra_pad) % 360.0
    ra_hi = (ra_deg + ra_pad) % 360.0

    def _ra_range(lo: float, hi: float) -> list[float]:
        vals: list[float] = []
        if lo <= hi:
            v = lo
            while v <= hi:
                vals.append(v)
                v += ra_step
        else:  # wraps past 360
            v = lo
            while v < 360.0:
                vals.append(v)
                v += ra_step
            v = 0.0
            while v <= hi:
                vals.append(v)
                v += ra_step
        return vals

    def _dec_range(lo: float, hi: float) -> list[float]:
        vals: list[float] = []
        v = lo
        while v <= hi:
            vals.append(v)
            v += dec_step
        return vals

    out: set[int] = set()
    out.add(bucket(ra_deg, dec_deg, nside))
    for r in _ra_range(ra_lo, ra_hi):
        for d in _dec_range(dec_lo, dec_hi):
            out.add(bucket(r, d, nside))
    return sorted(out)


# ----------------------------------------------------------------------
# SQL-level cone search
# ----------------------------------------------------------------------
@dataclass
class Detection:
    """Minimal detection row as returned by :func:`cone_search`.

    Mirrors the columns listed in :mod:`rubin_hunter.detection_db.schema`.
    """

    detection_id: int
    alert_id: str
    ra: float
    dec: float
    mjd: float
    band: str
    psf_flux: float | None
    psf_flux_err: float | None
    snr: float | None
    reliability: float | None
    streak_flag: int
    healpix_bucket: int
    ingest_time_utc: str


def _great_circle_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Haversine distance in arcseconds. Cheap and good enough here."""
    phi1 = math.radians(dec1)
    phi2 = math.radians(dec2)
    dphi = math.radians(dec2 - dec1)
    dlam = math.radians(ra2 - ra1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.asin(min(1.0, math.sqrt(a)))
    return math.degrees(c) * 3600.0


def cone_search(
    conn: sqlite3.Connection,
    ra_deg: float,
    dec_deg: float,
    radius_arcsec: float,
    nside: int = DEFAULT_NSIDE,
) -> list[Detection]:
    """Return detections within ``radius_arcsec`` of ``(ra, dec)``.

    Uses the precomputed ``healpix_bucket`` column to constrain the SQL
    scan, then applies an exact great-circle filter in Python. This is
    the F4 acceptance test in PRD §7.
    """
    buckets = cone_buckets(ra_deg, dec_deg, radius_arcsec, nside=nside)
    if not buckets:
        return []

    # SQLite 3.32+ supports parameter lists of arbitrary length, but we
    # chunk to stay well under the 32k-parameter default limit.
    out: list[Detection] = []
    chunk_size = 900
    for i in range(0, len(buckets), chunk_size):
        chunk = buckets[i : i + chunk_size]
        placeholders = ",".join(["?"] * len(chunk))
        sql = f"""
            SELECT detection_id, alert_id, ra, dec, mjd, band,
                   psf_flux, psf_flux_err, snr, reliability,
                   streak_flag, healpix_bucket, ingest_time_utc
              FROM detections
             WHERE healpix_bucket IN ({placeholders})
        """
        for row in conn.execute(sql, chunk):
            d = Detection(*row)
            if _great_circle_arcsec(ra_deg, dec_deg, d.ra, d.dec) <= radius_arcsec:
                out.append(d)
    return out
