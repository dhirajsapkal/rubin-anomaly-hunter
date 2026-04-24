"""CLI: run the live-ish pipeline once against Lasair-LSST.

Usage (from repo root):

    set LASAIR_TOKEN=your-token-here   # Windows cmd
    python scripts/run_live_pipeline.py

    python scripts/run_live_pipeline.py --since-days 2 --limit 50
    python scripts/run_live_pipeline.py --db-path data/live.sqlite

Environment variables
---------------------
LASAIR_TOKEN
    Your Lasair-LSST API token. Register at
    https://lasair.lsst.ac.uk/register and copy the token from your
    profile. Without it, Lasair returns 401 on every endpoint.

HELIOLINC3D_PATH / FINDORB_PATH
    Optional. If these binaries are installed, the wrappers pick them
    up. Without them, the pipeline runs in mock mode (loud warning
    banners on the dashboard).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Make `src/` importable without requiring an editable install.
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rubin_hunter.pipeline import (  # noqa: E402
    DEFAULT_ARCHIVE_ROOT,
    DEFAULT_LIVE_DB,
    run_once,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_LIVE_DB)
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    parser.add_argument("--since-days", type=float, default=1.0)
    parser.add_argument("--min-det", type=int, default=2)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument(
        "--ingest",
        choices=("lasair", "fink"),
        default=os.environ.get("RUBIN_HUNTER_INGEST", "lasair"),
        help="Ingest source. lasair = REST (ADR-0013, aggregate-only); "
        "fink = Kafka (ADR-0016, per-detection). Defaults to $RUBIN_HUNTER_INGEST.",
    )
    parser.add_argument(
        "--fink-topic",
        default=os.environ.get("FINK_TOPIC", "fink_uniform_sample_lsst"),
        help="Kafka topic when --ingest=fink.",
    )
    parser.add_argument(
        "--fink-config",
        type=Path,
        default=Path(os.environ["FINK_CLIENT_CONFIG"]) if os.environ.get("FINK_CLIENT_CONFIG") else None,
        help="Path to your fink-client YAML credentials. Falls back to fink-client's default resolution (~/.finkclient/credentials.yml).",
    )
    parser.add_argument("--fink-max-messages", type=int, default=200)
    parser.add_argument("--fink-timeout-s", type=float, default=30.0)
    parser.add_argument(
        "--fink-group-id",
        default=os.environ.get("FINK_GROUP_ID", "rubin-hunter-personal"),
        help="Kafka consumer-group id. Use a fresh id (e.g. "
        "'rubin-hunter-replay-1234') combined with --fink-offset-reset=earliest "
        "to replay messages still in Fink's Kafka retention window.",
    )
    parser.add_argument(
        "--fink-offset-reset",
        choices=("latest", "earliest"),
        default=os.environ.get("FINK_OFFSET_RESET", "latest"),
        help="auto.offset.reset for a NEW consumer group. 'latest' (default) "
        "= only new messages after subscribe. 'earliest' = replay from the "
        "start of Kafka's retention window — use for one-shot catch-up runs.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-7s %(name)s :: %(message)s",
    )

    if args.ingest == "lasair" and not os.environ.get("LASAIR_TOKEN"):
        print(
            "ERROR: --ingest=lasair but LASAIR_TOKEN is not set.\n"
            "  Set $LASAIR_TOKEN, or pass --ingest=fink.",
            file=sys.stderr,
        )
        return 2

    stats = run_once(
        db_path=args.db_path,
        archive_root=args.archive_root,
        since_days=args.since_days,
        min_det=args.min_det,
        limit=args.limit,
        ingest_mode=args.ingest,
        fink_topic=args.fink_topic,
        fink_group_id=args.fink_group_id,
        fink_config_path=args.fink_config,
        fink_max_messages=args.fink_max_messages,
        fink_timeout_s=args.fink_timeout_s,
        fink_offset_reset=args.fink_offset_reset,
    )

    print(json.dumps(stats.__dict__, indent=2, default=str))
    if stats.mock_mode_orbit or stats.mock_mode_linking:
        print(
            "NOTE: linking and/or orbit-fit ran in MOCK MODE — not\n"
            "      scientifically valid. Install heliolinc3d + find_orb\n"
            "      (Windows users: via WSL2) for real science outputs."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
