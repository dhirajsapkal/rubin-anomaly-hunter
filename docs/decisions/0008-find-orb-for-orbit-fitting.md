# ADR-0008 — find_orb for hyperbolic + non-grav orbit fitting

**Status:** Accepted
**Date:** 2026-04-22

## Context

The project needs to fit hyperbolic orbits (e > 1) with uncertainty propagation and Marsden-Sekanina non-gravitational terms (A1, A2, A3) on short arcs. The Python library landscape as of 2026:

- `poliastro` — **archived** as of 14 October 2023. Its fork `hapsira` is maintained but astrodynamics-focused, not a short-arc astrometric fitter.
- `REBOUND` + `REBOUNDx` — excellent propagator with non-grav force support, but not an astrometric fitter.
- `sbpy` — active astropy affiliate, wraps `pyoorb`/OpenOrb for statistical ranging; no native Marsden A1/A2/A3 fit.
- `find_orb` (Bill Gray, Project Pluto) — canonical tool used by MPC-submitting astronomers. Actively maintained. Supports: hyperbolic via the 'I' designation; Marsden A1/A2/A3 (+ optional DT); covariance sigmas; Monte Carlo and statistical ranging for short arcs; batch operation via the `fo` tool with JSON output.

## Decision

Call `find_orb` via Python subprocess — specifically the `fo` batch mode — for every tracklet. Plumb data in and out using `sbpy` for ADES format I/O. Parse JSON output for orbital elements and covariance.

## Consequences

- **Licensing: `find_orb` is source-available but NOT OSI-open.** Redistribution requires Bill Gray's explicit permission. Personal use is fine per ADR-0002 (personal-tool scope).
- **Do NOT include `find_orb` binaries, source, or derived ephemeris files in this repository** under any circumstance. Installation is a user-local setup step.
- If the project ever becomes open-source or externally redistributed, this ADR must be revisited and likely superseded with a migration to an OSI-licensed alternative (if one emerges).
- External binary dependency — build from source or download Project Pluto's Windows binary. Requires planetary-ephemeris files (e.g., `ELP82.DAT`). Pin versions.
- Fallback to WSL2 acceptable if Windows-native build misbehaves.
- Integration pattern is the same as `heliolinc3d` (ADR-0007): ADES in, JSON out, parse in Python.

## Alternatives considered

- **poliastro.** Rejected — archived, no short-arc fitter.
- **REBOUND + REBOUNDx.** Rejected — propagator, not fitter.
- **sbpy's OpenOrb wrapper.** Rejected — statistical ranging is useful as an orthogonal sanity check, but no native Marsden fit.
- **Custom Python fitter.** Rejected — months of domain expertise for a solved problem; we would not exceed Gray's implementation.
- **find_orb as a web-service call (Project Pluto online form).** Rejected — offline reproducibility is a project requirement; we must not depend on an external web service for the science path.

## References

- PRD §6, §7 F6, §12, §14 (licensing risk entry)
- Second-round research agent output, 2026-04-22
- https://www.projectpluto.com/find_orb.htm
- https://projectpluto.com/force.htm (Marsden non-grav documentation)
