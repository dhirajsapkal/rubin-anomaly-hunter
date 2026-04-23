# ADR-0013 — Lasair-LSST REST as interim ingest path

**Status:** Accepted (role demoted from "default ingest" to "fallback" — see ADR-0016)
**Date:** 2026-04-22
**Supersedes:** (none)
**Superseded by:** [ADR-0016](0016-fink-kafka-primary-ingest.md) — Fink Kafka becomes the primary ingest; Lasair REST remains a valid fallback for offline/no-creds development.

## Context

PRD §6 and ADR-0003 designate Fink + Lasair-LSST as the two live taps
for Rubin public alerts. The production plan is a Fink Kafka consumer
(`fink-client`, topic `fink_uniform_sample_lsst` at M0; a dedicated SSO
topic at M10). On Windows 11 — this project's target platform — the
Kafka stack has been fragile in practice: `confluent-kafka` wheel
installs, SASL cert paths, and the documented WSL2 fallback all add
setup steps before any alert flows. The user wants real Rubin alerts in
the dashboard today.

Lasair-LSST exposes the same Rubin alert stream via an HTTPS SQL query
endpoint and a per-object detail endpoint. Signup is free and takes
under two minutes; queries then require a bearer token. HTTPS is
first-class on Windows. This gives us a bridge: real data today via
Lasair REST, migrate to Fink Kafka once the SSO topic ships and the
Windows setup is smoothed out.

## Decision

Add `src/rubin_hunter/ingest/lasair_rest.py` as the M0-bridge ingest
path and wire the end-to-end pipeline (`src/rubin_hunter/pipeline.py`)
to it. Keep the Fink Kafka consumer (`ingest/fink_consumer.py`) in
place as the production target — this ADR adds a sibling path, it does
not retire the Fink one.

## Consequences

**New capabilities**

- Real Rubin alerts flow into `data/live.sqlite` on Windows without
  Kafka, without a local build toolchain, and with an ~2-minute signup
  for the Lasair token.
- Dashboard reads `live.sqlite` automatically when it exists (see
  `dashboard/lib/db.resolve_db_path`); the synthetic `demo.sqlite`
  stays available as a fallback so first-run remains empty-state-safe.
- Raw Lasair responses persist verbatim to the Parquet archive per
  ADR-0009 (no divergence from the reproducibility invariant).

**New obligations**

- The pipeline must tolerate Lasair's schema drift. Candidate field
  names (`psFlux`/`psflux`, `midpointMjdTai`/`mjd`) vary by release;
  the normaliser in `pipeline._object_poll_to_detections` accepts both.
- Token management: `LASAIR_TOKEN` env var is read at process start.
  Operator is responsible for rotation. The token is never written to
  `data/` or committed — the `.gitignore` already excludes `.token`.
- Rate limits: Lasair's anonymous tier caps queries at 5/minute; with a
  token the cap is generous but not infinite. The pipeline is designed
  around one `run_once()` per scheduling cycle (e.g. once per night),
  not a polling loop.

**Invariants this code depends on**

- ADR-0005: `pipeline._gate` never assigns `status='accept'` or
  `'promoted'`. The orchestrator enforces this with a runtime guard
  before any watch_list INSERT.
- ADR-0009: raw payloads land in the Parquet archive before
  normalisation touches them. The orchestrator order is:
  Lasair poll → `RawAlertArchive.append` → detection-row extraction.
  Reversing this order is an invariant breach.
- ADR-0003: only Rubin alerts drive watch-list entries. Lasair-LSST
  serves Rubin; switching to ZTF Lasair would violate this ADR.

**Migration path to Fink Kafka (M0-final)**

When Fink's SSO-dedicated Rubin topic is available and `fink-client`
installs cleanly on the operator's host:

1. Add a second orchestrator branch selecting `FinkConsumer` over
   `LasairRestConsumer` via a `RUBIN_HUNTER_INGEST` env var (`lasair`
   vs. `fink`).
2. Benchmark both on the same observing night and confirm parity.
3. Write ADR-0014 flipping the default to Fink and marking this ADR
   **Superseded by ADR-0014**.

This ADR is written so the bridge can be retired without regret — the
REST client, archive writer, detection normaliser, and gate are all
independent of the Kafka/REST choice.

## Alternatives considered

- **Fink Kafka via `fink-client` today.** Rejected for this session:
  needs working confluent-kafka on Windows, a Fink account, TLS
  credentials, and the Rubin SSO topic (which as of 2026-04 may still
  be running as `fink_uniform_sample_lsst`). Each of those is
  tractable; together they're a multi-session setup before any alert
  flows. Deferred to M0-final.
- **Public sample AVRO replay only.** Rejected — PRD §15 calls the
  empty/low-N state the *expected* state, but "expected" and
  "replaying canned data" are not the same. Sample replay remains
  available via `FinkConsumer` offline mode for unit tests.
- **Rubin Science Platform (RSP) / Butler / DP1 direct access.**
  Rejected by ADR-0010 — this project is alert-stream-only, not a
  data-rights holder.
- **ZTF alerts via Fink's public REST (`api.fink-portal.org`).**
  Rejected by ADR-0003 — ZTF is a calibration rail, never a driver of
  watch-list promotions. Using ZTF to populate real-looking entries
  would quietly breach the invariant.
- **Paid / hosted Lasair or Antares broker.** Out of scope for a
  personal tool (ADR-0002).

## References

- PRD §6 (ingest), §8 N5 (reproducibility), §13 M0
- ADR-0003 (Rubin primary, ZTF calibration-only)
- ADR-0005 (two-stage gate)
- ADR-0009 (own detection-history layer + raw-payload persistence)
- ADR-0010 (alert-only, no RSP access)
- Lasair-LSST API: https://lasair.lsst.ac.uk/api
- Fink LSST portal: https://lsst.fink-portal.org
