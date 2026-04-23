# ADR-0009 — Own detection-history layer

**Status:** Accepted
**Date:** 2026-04-22

## Context

The Rubin alert schema provides `prv_diaSources` — a nominal 12-month detection history for each alert. In early operations (first ~2 months of alert production), this field is often empty or sparse for Solar System objects:

- Fink's own filter code (`fink_filters/rubin/utils.py`) comments: *"Objects with no diaObject, such as SSO, return NaN."*
- DIA templates are still being built for many fields; first-epoch detections have no template history to subtract against.
- Alert production only started 24 February 2026 — even if history were always populated, only two months of baseline exist as of this ADR.

Short-arc orbit fits (ADR-0008) require multi-epoch astrometry on the same object. We cannot depend on broker-supplied history for the science path.

Separately, broker cross-match flags (SIMBAD tags, MPC tags, ALeRCE classification probabilities) drift over time as brokers update their cross-match databases. Querying broker context at review time can yield different answers than at ingest time for the same alert ID.

## Decision

Pipeline maintains its own detection database (SQLite with HEALPix bucket index) that accumulates every SSO-candidate detection across all nights of ingest. Tracklet linking (ADR-0007) runs on this local database, not on broker-supplied history.

Broker-supplied history fields are consumed when present for informational use, but never trusted as authoritative. Broker cross-match flags are **snapshotted at ingest time** into the local record and never re-queried in place — re-query only happens during review and produces a new annotation, never an in-place overwrite.

## Consequences

- Detection DB is load-bearing for the entire pipeline. Backups and integrity-check routines are required.
- Storage cost is modest: ~30 GB/year early-ops, scaling to ~200–300 GB/year at full LSST cadence (alert archive + detection rows).
- Reproducibility benefits — we can re-run linking with updated `heliolinc3d` parameters against the complete historical detection set at any point.
- Broker outages do not corrupt historical data we have already ingested.
- Raw alert payloads (AVRO bytes) are persisted verbatim at ingest — the invariant cited in CLAUDE.md depends on this ADR.
- HEALPix bucketing (nside=2^14 or similar — tune in commissioning) gives O(log N) cone-search queries; avoid B-tree-on-RA-Dec which fails at cone-search.

## Alternatives considered

- **Rely on broker history.** Rejected — sparse in early ops, inconsistent across brokers, drifting cross-match flags.
- **No local DB, re-query broker each night.** Rejected — no reproducibility; broker context drifts.
- **Hybrid: use broker history when populated, local history otherwise.** Rejected — adds complexity without payoff; local-always is simpler and more defensible.
- **SpatiaLite instead of HEALPix.** Viable; HEALPix preferred for astronomy-native spatial semantics but SpatiaLite could substitute if HEALPix tuning proves awkward.
- **PostgreSQL + Q3C extension.** Rejected for v1 — overkill for single-machine scope; could be a future upgrade at full LSST cadence if SQLite+HEALPix hits limits.

## References

- PRD §4, §6 stage 3, §8 N5
- Second-round research agent output, 2026-04-22 (Fink `rubin/utils.py` code inspection)
- Peer-review agent output, 2026-04-22 (broker-flag drift warning)
