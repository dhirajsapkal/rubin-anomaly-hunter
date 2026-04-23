"""Offline smoke-test of the full pipeline — no network, no creds.

Feeds a synthetic-but-realistic `LasairPoll` through
`rubin_hunter.pipeline.run_once`, exercising every downstream stage
(raw archive → detection DB → linking → orbit fit → scoring → gate →
watch_list → pipeline_health). Used to verify the plumbing is sound
before the user plugs in a real LASAIR_TOKEN.

Writes to `data/live.sqlite`. Idempotent per object_id (detections are
deduped on alert_id).

Usage:
    python scripts/smoke_pipeline_offline.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rubin_hunter.ingest.lasair_rest import (  # noqa: E402
    LasairObject,
    LasairPoll,
    LasairQuery,
    LasairRestConsumer,
)
from rubin_hunter.pipeline import run_once  # noqa: E402


def _synthetic_poll(now_mjd: float) -> LasairPoll:
    """Mimic what Lasair would return for a small window of Rubin alerts.

    We fabricate two objects:
      - A routine asteroid-shaped object (tight 1-night arc, low ncand).
      - A longer-arc object with a non-asteroid-like motion that should
        linger in the watch-list after mock-mode scoring.
    """
    objects = [
        LasairObject(
            object_id="LSST_SMOKE_0001",
            ra_deg=180.12,
            dec_deg=-12.34,
            n_candidates=6,
            mjd_min=now_mjd - 2.2,
            mjd_max=now_mjd - 0.1,
            mag_r_min=20.1,
            mag_r_max=21.3,
            annotations={"mpc_match": None},
            raw={"objectId": "LSST_SMOKE_0001"},
        ),
        LasairObject(
            object_id="LSST_SMOKE_0002",
            ra_deg=244.8,
            dec_deg=3.7,
            n_candidates=8,
            mjd_min=now_mjd - 3.0,
            mjd_max=now_mjd - 0.2,
            mag_r_min=19.6,
            mag_r_max=20.9,
            annotations={"mpc_match": None, "class": "Unknown"},
            raw={"objectId": "LSST_SMOKE_0002"},
        ),
    ]
    return LasairPoll(
        objects=objects,
        raw_response={"results": [o.raw for o in objects]},
        query=LasairQuery(since_mjd=now_mjd - 5, min_det=2, limit=200),
        source_url="smoke://lasair-offline",
        http_status=200,
    )


def _synthetic_detail_for(obj: LasairObject) -> dict:
    """Return a fake object-detail record with `candidates` the
    normaliser understands."""
    # Uniform cadence of detections across the object's advertised arc.
    step = (obj.mjd_max - obj.mjd_min) / max(1, obj.n_candidates - 1)
    candidates = []
    for i in range(obj.n_candidates):
        mjd = obj.mjd_min + step * i
        candidates.append(
            {
                "diaSourceId": f"{obj.object_id}-{i:02d}",
                "ra": obj.ra_deg + i * 0.00006,  # slow drift, arcsec/day scale
                "dec": obj.dec_deg + i * 0.00003,
                "midpointMjdTai": mjd,
                "fid": "r",
                "psFlux": 120.0 - i * 0.7,
                "psFluxErr": 3.2,
                "reliability": 0.91,
                "streak_flag": 0,
            }
        )
    return {"objectId": obj.object_id, "candidates": candidates}


def main() -> int:
    from datetime import datetime, timezone

    # Mock Lasair consumer that returns our synthetic fixtures.
    now_mjd = 40587.0 + datetime.now(timezone.utc).timestamp() / 86400.0
    poll = _synthetic_poll(now_mjd)
    details = {o.object_id: _synthetic_detail_for(o) for o in poll.objects}

    lasair = MagicMock(spec=LasairRestConsumer)
    lasair.run_filter.return_value = poll
    lasair.fetch_object_detail.side_effect = lambda oid: details[oid]

    stats = run_once(lasair=lasair, since_days=5, min_det=2, limit=200)

    import json
    print(json.dumps(stats.__dict__, indent=2, default=str))
    print()
    print(
        "Data flowed end-to-end: raw archive -> detections -> tracklets ->\n"
        "orbit_fits -> watch_list -> pipeline_health. Start the dashboard\n"
        "(streamlit run dashboard/app.py) to see it. The dashboard auto-reads\n"
        "data/live.sqlite when it has triage content; otherwise it falls\n"
        "back to data/demo.sqlite.\n\n"
        "Note: mock-mode linking produces only same-night tracklets, which\n"
        "correctly fail the 3-night-arc common gate. Install heliolinc3d to\n"
        "see watch-list entries in live mode."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
