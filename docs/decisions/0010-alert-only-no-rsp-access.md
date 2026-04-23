# ADR-0010 — Alert-stream-only access (no RSP/Butler/DP1)

**Status:** Accepted
**Date:** 2026-04-22

## Context

The Rubin Observatory has multiple data-access tiers:

- **Alert stream** — publicly distributed by nine community brokers. No data-rights required; anyone with an email can sign up.
- **Rubin Science Platform (RSP)** — JupyterLab + TAP + Butler at https://data.lsst.cloud. Requires a data-rights account via CILogon. US/Chile institutions and in-kind-contribution partners only.
- **Data Preview 1 (DP1)** — released 2025-06-30. Explicit policy: *"Only Rubin data rights holders may have an account in the Rubin Science Platform (RSP) and access to Data Preview 1."*
- **Data Release 1 (DR1)** — 2-year proprietary window; public only after embargo.

The user has no US/Chile Rubin-participating-institution affiliation and is not an in-kind contributor. There is no viable route to RSP / Butler / DP1 access for this project as of 2026-04-22.

## Decision

Pipeline is **alert-stream-only**. All science operates on what arrives in alert packets:

- Astrometry (RA, Dec, MJD)
- Photometry (psfFlux, apFlux per band)
- Features (~100 per alert — shape moments, reliability scores, trail metrics)
- 63×63 FITS cutouts (science / template / difference)

No pixel-level access beyond alert cutouts. No full-catalog TAP/ObsTAP queries. No Butler pipeline access.

## Consequences

- **Out of scope:** deep forced photometry, template inspection, bulk catalog cross-matching beyond what brokers provide, any pipeline step requiring raw image pixels.
- **In scope and sufficient:** dark-comet and ISO detection can be accomplished from astrometry + cutouts + alert features. Cross-matching against MPC and external catalogs is done via those catalogs' public endpoints, not via Rubin internal catalog access.
- This decision is **not irreversible.** If the user ever obtains data rights (e.g., via an affiliate institution), the pipeline can be extended with Butler/TAP subsystems. A new ADR would document that transition.
- Any attempt to work around data-rights restrictions (scraping rights-holder-only endpoints, sharing credentials, etc.) is explicitly prohibited — project must remain compliant with Rubin's data-access policy.

## Alternatives considered

- **Seek data rights via an affiliate institution.** Rejected for v1 — out of scope for a personal hobby project; may revisit later.
- **Wait for DR1 proprietary window to expire (~2028).** Rejected — two-year delay defeats the real-time-data goal.
- **Scrape any public endpoints that might exist.** Rejected — DP1 is not public for non-rights-holders; scraping would be non-compliant and dishonest.
- **Use only public papers/supplementary data with Rubin data.** Rejected as a primary source — too sparse, not real-time — but acceptable as a validation-input source (e.g., 3I/ATLAS astrometry from arXiv:2507.13409 supplementary materials).

## References

- PRD §2 non-goals, §4, §17
- Second-round research agent output, 2026-04-22 (data-rights policy verification)
- Rubin data policy LPM-261
- https://dp1.lsst.io (DP1 access policy)
