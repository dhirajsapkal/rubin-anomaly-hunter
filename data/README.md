# data/

Runtime data — **not committed to git**.

This directory holds:

- `demo.sqlite` — synthetic detection/tracklet/orbit-fit/watch-list DB produced by `scripts/make_demo_db.py`. Regenerate anytime.
- `raw_alerts/YYYY-MM-DD.parquet` — verbatim AVRO bytes + ingest-time broker-flag snapshots (per ADR-0009). When the live pipeline runs, one Parquet file per UTC day.
- `samples/*.avro` — offline Fink alert samples for dev mode (optional).

The `.gitignore` excludes all of this. Never commit science data.

## Regenerating the demo DB

```bash
python scripts/make_demo_db.py
```

This is deterministic (seeded from `configs/thresholds-commissioning.yaml`'s `anomaly_score.random_seed`), so re-running produces bit-identical content.
