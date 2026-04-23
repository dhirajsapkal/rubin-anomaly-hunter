# ADR-0016 — Fink Kafka as the primary ingest path

**Status:** Accepted
**Date:** 2026-04-23
**Supersedes:** ADR-0013 (Lasair REST as interim ingest path) — ADR-0013
stays accepted for offline/replay use; Fink Kafka takes over as the
default.
**Superseded by:** —

## Context

ADR-0013 introduced Lasair-LSST REST as an M0-bridge so real Rubin
alerts could flow into the dashboard today, without a Kafka stack on
Windows. That bridge worked, but the audit pass (2026-04-23) surfaced
a fundamental limitation: Lasair's `/api/query/` endpoint only exposes
the aggregate `objects` table — one `(ra, decl)` per object, replicated
across per-band `*_latestMJD` rows. There is no per-detection
astrometry over REST.

Per-detection astrometry is where `find_orb` lives. With only one sky
coordinate per object, every orbit fit is degenerate; the previous
implementation produced mock-noise fits that leaked into the watch list
as false positives. A subsequent "honesty gate" refactor made the
pipeline mark these as `undetermined` instead — which is the right
call, but it means the Lasair REST path can never produce a real flag.

Fink LSST's Kafka stream delivers full alert packets including
`diaSource` (the current detection) and `prvDiaSources` (the multi-night
history). That is what the scoring algorithm needs. Setup is tractable
— the bottleneck was `confluent-kafka` + SASL on Windows, which is why
we routed around it; now the project has a WSL2 build path and the
binaries (`find_orb`, `heliolinc3d`) install there too.

## Decision

Promote **Fink Kafka** to the **default ingest** when WSL2 +
`fink-client` credentials are available. Lasair REST remains a fallback
for offline/no-creds development, but watch-list promotion only happens
on per-detection data.

Specifically:

- `src/rubin_hunter/pipeline.run_once` takes an ``ingest_mode`` kwarg
  (``"lasair"`` | ``"fink"``). The CLI (`scripts/run_live_pipeline.py`)
  exposes `--ingest {lasair,fink}` defaulting to the
  `RUBIN_HUNTER_INGEST` env var.
- Fink ingest uses the existing `FinkConsumer` wrapper (now hardened to
  resolve `FINK_CLIENT_CONFIG` env var + `~/.finkclient/credentials.yml`
  fallbacks).
- A new `rubin_hunter.ingest.fink_ingest` module normalises each Fink
  alert's `diaSource` + `prvDiaSources` into the per-detection dict
  shape the rest of the pipeline expects. Deduped on `diaSourceId`.
- Raw alert payloads still persist verbatim to Parquet first (ADR-0009
  invariant unchanged).
- Broker cross-match flags (`cdsxmatch`, `mpc_cross_match`, `sherlock`,
  etc.) are snapshotted into `broker_flags_json` at ingest time
  (ADR-0009, again unchanged).

WSL2 setup is scripted at `scripts/wsl/bootstrap.sh` — installs build
deps, builds `find_orb` + `heliolinc3d` under `~/src/`, creates a Python
venv with `fink-client`, and writes `~/.rubin-hunter.env` that the
pipeline sources to locate binaries + venv.

## Consequences

**New capabilities**

- Real multi-night arcs arrive with every alert via `prvDiaSources`.
- `find_orb` can produce real fits with non-grav Marsden terms; the
  dark-comet scorer (which depends on `A1/A2/A3`) becomes meaningful
  for the first time.
- `heliolinc3d` cross-night linking can run on real detections.
- `ORBITS` provenance chip flips from `UNDETERMINED` to `REAL` as soon
  as one alert has been through the full path.

**New obligations**

- The operator needs a registered Fink account. Unregistered state
  drops the consumer to offline-replay (sample AVRO under
  `data/samples/`); production promotion never runs on sample replay.
- Windows operators must run the WSL bootstrap once. `confluent-kafka`
  builds cleanly on Ubuntu 24.04 inside WSL; the native Windows build
  is NOT supported (fragile wheels).
- `find_orb` binaries live under `~/src/find_orb/` in WSL — **never
  committed** (ADR-0008 invariant).

**Invariants preserved**

- ADR-0005 (two-stage gate, strict language discipline): unchanged.
- ADR-0008 (find_orb personal-use-only): unchanged. Binaries are
  built locally, never redistributed.
- ADR-0009 (raw payloads persist verbatim, broker flags snapshotted at
  ingest, never re-queried in place): unchanged.
- ADR-0010 (alert-only — no RSP / pixel access): unchanged. Fink Kafka
  delivers alert packets, not pixel cutouts.
- ADR-0013 (Lasair REST): status stays Accepted; role demoted from
  "default ingest" to "offline/fallback".

**Honest labelling**

- When `ingest_mode="fink"` and `find_orb`/`heliolinc3d` are both
  installed, the provenance chips read `INGEST: LIVE · ORBITS: REAL`.
- When `ingest_mode="fink"` but binaries are missing, chips read
  `INGEST: LIVE · ORBITS: MOCK` (with scoped per-value provenance on
  the canvas entries).
- When `ingest_mode="lasair"`, chips read `INGEST: LIVE · ORBITS:
  UNDETERMINED` regardless of binary state — the inputs can't support
  a real fit even with a working `find_orb`.

## Alternatives considered

- **Stay on Lasair REST and build a native Python orbit fitter (Gauss
  IOD).** Rejected. Lasair REST still has no per-detection data, so
  the fitter would have nothing to fit. A Python fitter is a
  worthwhile follow-up but doesn't solve the data gap.
- **Lasair Kafka instead of Fink Kafka.** Considered. Lasair does have
  a Kafka interface but the LSST shard's topic list is sparser and the
  credentials setup is identical effort. Fink's classification layer
  (SIMBAD, MPC Checker, roid, Sherlock) is richer out of the box.
- **ALeRCE broker.** ALeRCE has an API but the LSST integration is
  less mature than Fink's. Revisit in a year.
- **Direct Rubin alert stream (bypass broker).** Rubin's own public
  alert stream is Kafka with TLS + a dedicated username — same
  operational cost as Fink. Fink adds value (classifications); using
  the broker is the pragmatic call for a personal tool.

## References

- PRD §§4, 6, 13 (milestone M0 definition)
- ADR-0003 (Rubin primary, ZTF calibration-only)
- ADR-0005, 0007, 0008, 0009, 0010, 0013
- Fink LSST docs: https://fink-broker.readthedocs.io
- LSST alert schema: https://github.com/lsst/alert_packet
- WSL2 bootstrap script: `scripts/wsl/bootstrap.sh`
