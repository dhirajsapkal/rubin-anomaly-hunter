"""Lasair-LSST REST consumer — interim ingest path per ADR-0013.

Why REST (not Kafka) for M0-bridge
----------------------------------
Fink's LSST Kafka stream (`fink_uniform_sample_lsst`) is the production
tap, but it requires a `fink-client` account and a working Kafka consumer
on the host. On Windows 11 (this project's target platform) that stack
has been fragile in practice. Lasair-LSST exposes the same underlying
alert stream via an HTTPS SQL endpoint with no account required for
read-only queries — so we use it to get real Rubin alerts into the
dashboard today, and graduate to Fink Kafka in a follow-up session.

This module is intentionally narrow:

* One method, :meth:`LasairRestConsumer.run_filter`, which evaluates a
  Lasair SQL filter over a bounded time window and returns decoded
  object records.
* The returned dicts are the Lasair object payload verbatim — *no*
  normalisation happens here. Normalisation into the detection DB shape
  is the pipeline orchestrator's job (`rubin_hunter.pipeline`).
* Per ADR-0009 the caller must persist the raw payloads before any
  filtering or transformation.

References
----------
- Lasair-LSST API docs: https://lasair.lsst.ac.uk/api
- ADR-0013 (this commit): Lasair REST as interim ingest path
- ADR-0003: Rubin primary / ZTF calibration-only
- ADR-0009: raw alert payloads persist verbatim at ingest
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

try:
    import requests  # type: ignore
    _HAVE_REQUESTS = True
except Exception:  # pragma: no cover
    requests = None  # type: ignore
    _HAVE_REQUESTS = False


logger = logging.getLogger(__name__)


LASAIR_DEFAULT_BASE = "https://lasair.lsst.ac.uk"
LASAIR_TOKEN_ENV = "LASAIR_TOKEN"


# Lasair-LSST only exposes the aggregate `objects` table through
# `/api/query/` — per-detection astrometry is not available over REST
# (it lives in the Kafka stream). We work around this in the pipeline
# orchestrator by synthesising per-band detection rows from the
# aggregate's `*_latestMJD` columns. See ADR-0013 for the trade-off.
#
# Real LSST `objects` table columns (as of 2026-04):
#   diaObjectId, ra, decl, firstDiaSourceMjdTai, lastDiaSourceMjdTai,
#   nDiaSources, medianR, latestR, glat, htm16,
#   {u,g,r,i,z,y}_latestMJD, {u,g,r,i,z,y}_psfFlux{,Mean,MeanErr,Sigma,Ndata}
#
# The pre-filter below is inclusive (PRD §6) — wide net at ingest,
# scoring modules decide what's interesting downstream.
DEFAULT_SELECTED = (
    "diaObjectId, ra, decl, "
    "firstDiaSourceMjdTai, lastDiaSourceMjdTai, nDiaSources, "
    "medianR, latestR, glat, "
    "u_latestMJD, u_psfFlux, u_psfFluxMean, u_psfFluxMeanErr, u_psfFluxSigma, "
    "g_latestMJD, g_psfFlux, g_psfFluxMean, g_psfFluxMeanErr, g_psfFluxSigma, "
    "r_latestMJD, r_psfFlux, r_psfFluxMean, r_psfFluxMeanErr, r_psfFluxSigma, "
    "i_latestMJD, i_psfFlux, i_psfFluxMean, i_psfFluxMeanErr, i_psfFluxSigma, "
    "z_latestMJD, z_psfFlux, z_psfFluxMean, z_psfFluxMeanErr, z_psfFluxSigma, "
    "y_latestMJD, y_psfFlux, y_psfFluxMean, y_psfFluxMeanErr, y_psfFluxSigma, "
    "tns_name"
)
DEFAULT_TABLES = "objects"


@dataclass
class LasairQuery:
    """Parameters for a single Lasair SQL-filter invocation.

    Lasair's `/api/query/` API takes structured ``selected`` / ``tables`` /
    ``conditions`` fields — NOT a single SQL blob. We build the WHERE
    clause from ``since_mjd`` + ``min_det`` + ``conditions_extra``.
    """

    since_mjd: float
    min_det: int = 2
    limit: int = 200
    # Optional extra WHERE clause segments — appended with AND.
    conditions_extra: str | None = None
    selected: str = DEFAULT_SELECTED
    tables: str = DEFAULT_TABLES

    def conditions(self) -> str:
        parts = [
            f"lastDiaSourceMjdTai >= {self.since_mjd:.5f}",
            f"nDiaSources >= {int(self.min_det)}",
        ]
        if self.conditions_extra:
            parts.append(f"({self.conditions_extra})")
        return " AND ".join(parts)


@dataclass
class LasairObject:
    """One aggregate-object row from the Lasair-LSST `objects` table.

    ``raw`` preserves the full unmodified record so ADR-0009 compliance
    holds end-to-end. The orchestrator uses the per-band fields on the
    raw dict to synthesise detection rows at archive-write time.
    """

    object_id: str
    ra_deg: float
    dec_deg: float
    n_candidates: int
    mjd_min: float
    mjd_max: float
    mag_r_min: float | None = None   # no longer populated from objects; kept for compat
    mag_r_max: float | None = None
    annotations: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    reliability: float | None = None
    tns_name: str | None = None


@dataclass
class LasairPoll:
    """Bundle returned by :meth:`LasairRestConsumer.run_filter`.

    Includes the objects plus the raw API response body for audit /
    replay. Keep the raw bytes around — the orchestrator passes them to
    :class:`RawAlertArchive` per ADR-0009 before doing anything else.
    """

    objects: list[LasairObject]
    raw_response: dict[str, Any]
    query: LasairQuery
    source_url: str
    http_status: int


class LasairRestConsumer:
    """Thin HTTPS client over the Lasair-LSST SQL query endpoint.

    Parameters
    ----------
    base_url
        Lasair site root; defaults to the public LSST shard.
    token
        Optional API token. Read-only SQL queries work without one; we
        send it when present because it raises the rate limit ceiling.
    session
        Optional pre-constructed ``requests.Session`` for connection
        reuse / test injection.
    timeout_s
        Per-request HTTP timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = LASAIR_DEFAULT_BASE,
        *,
        token: str | None = None,
        session: "requests.Session | None" = None,
        timeout_s: float = 30.0,
    ) -> None:
        if not _HAVE_REQUESTS:
            raise RuntimeError(
                "`requests` is required for LasairRestConsumer. "
                "pip install requests"
            )
        self.base_url = base_url.rstrip("/")
        self.token = token or os.environ.get(LASAIR_TOKEN_ENV)
        self.session = session or requests.Session()
        self.timeout_s = timeout_s

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run_filter(self, query: LasairQuery) -> LasairPoll:
        """Execute a structured SQL query against the Lasair objects table.

        Lasair's `/api/query/` wants three discrete fields — ``selected``,
        ``tables``, ``conditions`` — not a single SQL string. Sending the
        whole SQL blob under ``selected`` yields HTTP 400.

        Per ADR-0009 the caller persists the raw response before touching
        the decoded objects. The returned :class:`LasairPoll` keeps the
        raw body for that purpose.
        """
        url = f"{self.base_url}/api/query/"
        params = {
            "selected": query.selected,
            "tables": query.tables,
            "conditions": query.conditions(),
            "limit": str(query.limit),
        }
        headers = {}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        logger.info("Lasair query: %s  conditions=%s", url, params["conditions"])
        resp = self.session.get(
            url,
            params=params,
            headers=headers,
            timeout=self.timeout_s,
        )
        status = resp.status_code
        if status >= 400:
            raise RuntimeError(
                f"Lasair returned HTTP {status}: {resp.text[:500]}"
            )
        try:
            body = resp.json()
        except ValueError as exc:
            raise RuntimeError(f"Lasair body is not JSON: {exc}") from exc

        rows = body if isinstance(body, list) else body.get("results", [])
        objects = [self._to_object(r) for r in rows if isinstance(r, dict)]
        return LasairPoll(
            objects=objects,
            raw_response={"results": rows} if isinstance(body, list) else body,
            query=query,
            source_url=f"{url}?{urlencode(params)}",
            http_status=status,
        )

    def fetch_object_detail(self, object_id: str) -> dict[str, Any]:
        """Not available over Lasair-LSST REST — kept as a shim.

        Per-detection astrometry is only exposed via the Fink Kafka
        stream; `/api/query/` rewrites any table name to the aggregate
        `objects` table. This shim returns an empty dict so calling
        code can stay branch-free. See ADR-0013.
        """
        return {}

    # ------------------------------------------------------------------
    # Decoding
    # ------------------------------------------------------------------
    @staticmethod
    def _to_object(row: dict[str, Any]) -> LasairObject:
        """Decode a Lasair `objects` row into our dataclass.

        Real Lasair-LSST field names (2026-04):
          ``diaObjectId`` · ``ra`` · ``decl`` · ``nDiaSources`` ·
          ``firstDiaSourceMjdTai`` · ``lastDiaSourceMjdTai`` ·
          ``medianR`` · ``latestR`` · ``tns_name``

        Legacy ZTF-era names (``objectId``, ``ramean``, ``decmean``,
        ``ncand``, ``mjdmin/max``) are tried as fallbacks so unit tests
        with fixture data from the old schema still load.
        """
        ra = row.get("ra", row.get("ramean"))
        dec = row.get("decl", row.get("decmean", row.get("dec")))
        return LasairObject(
            object_id=str(
                row.get("diaObjectId")
                or row.get("objectId")
                or row.get("object_id")
                or ""
            ),
            ra_deg=float(ra) if ra is not None else float("nan"),
            dec_deg=float(dec) if dec is not None else float("nan"),
            n_candidates=int(
                row.get("nDiaSources")
                or row.get("ncand")
                or row.get("n_candidates")
                or 0
            ),
            mjd_min=float(
                row.get("firstDiaSourceMjdTai")
                or row.get("mjdmin")
                or 0.0
            ),
            mjd_max=float(
                row.get("lastDiaSourceMjdTai")
                or row.get("mjdmax")
                or 0.0
            ),
            reliability=_opt_float(row.get("latestR") or row.get("medianR")),
            tns_name=row.get("tns_name"),
            raw=row,
        )


def _opt_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
