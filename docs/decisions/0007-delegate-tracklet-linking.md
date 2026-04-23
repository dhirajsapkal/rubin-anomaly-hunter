# ADR-0007 — Delegate tracklet linking to heliolinc3d

**Status:** Accepted
**Date:** 2026-04-22

## Context

Tracklet linking — associating detections of the same moving object across nights — is a published hard problem with established solutions:

- Kubica et al. 2007 (MOPS) introduced tree-based linking.
- Holman et al. 2018 / Heinze et al. 2022 extended the approach as HelioLinC3D, which is the Rubin-era standard.

Naive pair-linking is O(N²) per night and combinatorially worse across nights. At LSST cadence (~10 M alerts/night at full survey, ~100 k–1 M SSO candidates after pre-filter), naive implementation is infeasible on a single machine.

Peer review flagged that the initial plan's "nightly SQLite dedup + linking" description glossed over this combinatorics problem.

## Decision

Call **`heliolinc3d`** as a Python subprocess on the rolling detection window. Do not implement tree-based linking in Python. Use the same subprocess integration pattern as `find_orb` (ADR-0008).

Repo: https://github.com/lsst-dm/heliolinc2

## Consequences

- External tool dependency. C++ build. Windows compilation may be non-trivial; **WSL2 is the documented fallback** (cf. PRD §12, §14).
- Linking quality is bounded by `heliolinc3d` parameters, which the project must learn to tune. Tuning is a calibration-window task.
- We avoid months of reimplementation for a solved problem.
- Detection DB schema must output input rows in the format `heliolinc3d` expects (astrometry + time + quality flags); wrapper code translates.
- Upstream parameter changes to `heliolinc3d` could affect reproducibility; pin the commit/version used.

## Alternatives considered

- **Implement Kubica trees in Python.** Rejected — months of domain work for zero novelty; well-trodden ground.
- **Naive pair-linking with HEALPix pre-filtering.** Rejected — still effectively O(N²); insufficient at scale.
- **Use broker-side tracklets only.** Rejected — brokers do not yet expose LSST-native tracklet services at a useful granularity.
- **Rust/Go reimplementation.** Rejected — same work as Python reimplementation; external tool is the right default.

## References

- PRD §6, §7 F5, §14 (Windows build risk)
- Peer-review agent output, 2026-04-22
- Holman et al. 2018 (HelioLinC)
- Heinze et al. 2022 (HelioLinC3D)
- Kubica et al. 2007 (MOPS)
