# ADR-0001 — Scope narrowing: from UAPs to ISO/dark-comet hunting

**Status:** Accepted
**Date:** 2026-04-22

## Context

The user originally proposed a pipeline over Rubin Observatory data to hunt for UAPs/UFOs. A four-agent parallel research phase established that Rubin is architecturally unsuited for classical atmospheric UAP phenomena:

- 8.4 m mirror focused at infinity
- 30-second exposures
- 9.6-square-degree field of view
- Slews every ~40 seconds (does not stare)

Anything at low altitude would be massively defocused, trailed across the entire exposure, or outside the field. The same research identified genuinely interesting Rubin-native anomaly classes: interstellar objects, dark comets, megastructure-style dimming, and variable-star technosignature candidates.

## Decision

Narrow the project scope from "UAP detection" to anomaly classes Rubin can actually detect. Initial framing: ISO hunting. Subsequently refined in ADR-0004 to dark comets (primary) + ISOs (secondary).

## Consequences

- Project becomes scientifically defensible rather than pareidolia-prone.
- Outputs have real-world value (dark-comet catalog contributions, ISO rapid-follow-up triggers) instead of existing only as spectacle.
- Project identity is explicit in all user-facing language: this is a Solar System anomaly hunter, not a UFO detector. PRD §17 enumerates this as out of scope.
- Any future pivot toward UAP-adjacent framing must pass through a new ADR.

## Alternatives considered

- **Drop the project entirely.** Rejected — real anomaly-hunt opportunity exists and the user wants a project that uses fresh Rubin data.
- **LEO satellite / non-astronomical fast-mover catalog.** Rejected — already addressed by LSSTC SatCon efforts; not interesting science.
- **Megastructure-dimming / Boyajian's-Star-style variable-star search.** Viable but rejected for v1 — user's interest was explicitly "fresh real-time Rubin data," not 10-year variability analysis. Could be a future sibling project.

## References

- PRD §1, §17
- Initial research phase, 2026-04-22 (four parallel agents: Rubin APIs, anomaly detection methods, UAP feasibility, Python stack)
- Galileo Project (Loeb) results cited in research phase as evidence for Rubin being wrong instrument for atmospheric UAPs
