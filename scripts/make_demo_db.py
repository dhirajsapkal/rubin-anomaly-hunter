"""CLI wrapper: wipe and regenerate ``data/demo.sqlite``.

Usage (from repo root)::

    python scripts/make_demo_db.py
    python scripts/make_demo_db.py --db-path data/custom.sqlite
    python scripts/make_demo_db.py --thresholds configs/other.yaml

Per ADR-0009 and ADR-0005, this script only produces **simulated**
data. It is never a substitute for the live ingest path, and none of
its watch-list entries are discovery claims.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make `src/` importable without requiring an editable install.
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rubin_hunter.demo.generate_demo_data import (  # noqa: E402
    DEFAULT_DEMO_DB_PATH,
    generate,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DEMO_DB_PATH,
        help=f"Target SQLite path (default: {DEFAULT_DEMO_DB_PATH}).",
    )
    parser.add_argument(
        "--thresholds",
        type=Path,
        default=None,
        help="Path to a thresholds YAML (default: configs/thresholds-commissioning.yaml).",
    )
    args = parser.parse_args(argv)

    out = generate(db_path=args.db_path, thresholds_path=args.thresholds)
    print(f"demo DB written to {out}")

    # Print a tiny summary so the user sees what landed.
    import sqlite3

    conn = sqlite3.connect(out)
    try:
        for table in (
            "detections",
            "tracklets",
            "orbit_fits",
            "watch_list",
            "decisions",
            "threshold_versions",
            "pipeline_health",
        ):
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table:<20} {n}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
