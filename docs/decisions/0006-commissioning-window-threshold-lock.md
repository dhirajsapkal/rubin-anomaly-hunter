# ADR-0006 — Commissioning window + dated threshold lock

**Status:** Accepted
**Date:** 2026-04-22

## Context

Original plan called for pre-registered numeric thresholds locked at v1 before any data ingest, modeled on HEP-style blinding. Peer review flagged this as cargo-cult rigor:

- HEP blinding works because Monte Carlo simulations are trusted.
- Rubin commissioning false-positive distributions are explicitly not trusted yet — brokers are still tuning, templates are still being built, and the observed noise structure in early-ops alerts will not match any pre-existing model.

Locking thresholds blind would yield either too-loose (flood of false positives) or too-tight (miss real objects) criteria, and in either case pseudo-rigor.

## Decision

A **commissioning window** runs from first ingest through a target date of **2026-07-01** (adjustable if plumbing delays justify). During this window:

- All pipeline stages run end-to-end.
- Thresholds (§5 of PRD) are fluid.
- Distributions of e, σ(e), non-grav residuals, null-field watch-list counts are characterized against observed Rubin data and ZTF archive replay.
- Nothing from this window counts as a discovery claim.

At the **threshold-lock date**, thresholds are frozen based on (a) observed commissioning distribution, (b) injection-test recall targets, (c) null-field false-positive budget. The configuration is committed to `configs/thresholds-v1.yaml` and **git-tagged immutable**.

The **discovery window** begins at the tag. Post-lock, only a new version number (`thresholds-v2.yaml` with new tag) permits change; pre-v2 watch-list entries remain evaluated under v1 rules.

## Consequences

- Split-sample design — calibration data never contaminates discovery claims.
- Threshold lock date is a target, not a contract. Push out rather than lock on unstable distributions.
- Git-tagged config is a load-bearing artifact. Never edit in place after the tag.
- Pre-lock watch-list entries are explicitly excluded from any external claim. PRD §15 lists this as a success-metric constraint.
- Any retrospective re-analysis must clearly label which threshold version applied.

## Alternatives considered

- **Hard pre-register at v1.** Rejected — cargo-cult; risks bad thresholds.
- **No threshold lock, iterate continuously.** Rejected — loses scientific defensibility; no clear line between calibration and discovery.
- **Rolling pre-registration (new thresholds every week).** Rejected — too clever, hard to audit, creates version-management nightmare.
- **Lock thresholds based on ZTF distributions only, use on Rubin.** Rejected — distributions are instrument-specific; Rubin's noise structure will differ.

## References

- PRD §5, §15, §13 M8
- Peer-review agent output, 2026-04-22
- Analogous split-sample designs in transient-survey literature (LSST DESC blinding policies)
