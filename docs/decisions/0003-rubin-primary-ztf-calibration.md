# ADR-0003 — Rubin primary, ZTF as calibration rail

**Status:** Accepted
**Date:** 2026-04-22

## Context

Initial plan was "ZTF now, Rubin later" under the assumption Rubin's public-alert availability was uncertain. Second-round research confirmed:

- Rubin alerts are fully public to non-rights-holders via Fink/Lasair/seven other brokers as of 24 February 2026.
- Early-ops volume (~800k/night) is single-machine ingestible.
- 3I/ATLAS has Rubin commissioning observations published (arXiv:2507.13409) — a Rubin-native validation target exists.

The user pushed back on the ZTF-first framing, asking to actually use fresh Rubin data. Peer review then flagged that fully dropping ZTF loses the ability to retrospectively inject 1I/'Oumuamua (2017) and 2I/Borisov (2019) — both predate Rubin operations — and that ZTF's archive-replay infrastructure (ANTARES, Kowalski) is mature while Rubin's is not.

## Decision

Rubin is the **primary science data source** — the only source that drives watch-list promotions.

ZTF is the **calibration rail only** — used to exercise tracklet-linking code on a live SSO stream while Rubin's SSO-specific Fink topic is absent, and to retrospectively inject historical ISOs (1I, 2I) that predate Rubin.

## Consequences

- Two ingest paths with strictly different roles. Any code that promotes ZTF data into the science path is an invariant violation.
- Validation plan uses both paths (V1 ZTF injection, V2 Rubin 3I/ATLAS rediscovery).
- When Fink ships a dedicated LSST SSO topic and Rubin's archive-replay story matures, ZTF's role can shrink further — worth a future ADR at that point.
- Schema normalization happens once at ingest; downstream stages see a unified event shape regardless of source.

## Alternatives considered

- **Rubin-only.** Rejected on reviewer advice — loses 1I/2I injection capability and mature ZTF replay tooling while Rubin archive tooling matures.
- **ZTF primary, Rubin secondary.** Rejected — defeats user's explicit goal of using fresh Rubin data; 3I/ATLAS Rubin commissioning data provides a Rubin-native validation target.
- **Dual-primary (both drive science).** Rejected — schema and cadence differences make joint science reasoning fraught; one-primary is cleaner.

## References

- PRD §4, §9
- Second-round research agent output, 2026-04-22 (Rubin alert access specifics)
- Peer-review agent output, 2026-04-22 (ZTF-calibration rationale)
