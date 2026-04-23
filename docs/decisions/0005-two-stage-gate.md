# ADR-0005 — Two-stage gate: watch-list → candidate

**Status:** Accepted
**Date:** 2026-04-22

## Context

Peer review flagged that any "we discovered an ISO" or "we discovered a dark comet" claim from alert-only data would be scientifically indefensible. Short-arc orbit fits cannot distinguish hyperbolic from high-eccentricity bound with small σ, and standalone non-grav residuals require external astrometry and multi-epoch imaging for full confirmation. Pretending alert-only data closes the case would generate false claims and embarrass the project.

## Decision

Candidacy is a two-stage gate:

- **Stage A — Watch-list.** Alert-only, real-time. An object is flagged if its best-fit orbit, non-grav residuals, and null-hypothesis-test outcomes meet the frozen thresholds.
- **Stage B — Candidate.** Requires external follow-up astrometry: subsequent Rubin passes with extended arc, amateur-network observations, or MPC-listed follow-up. Only Stage B status may be discussed externally as potentially novel.

## Consequences

- Pipeline's real-time value is flagging for follow-up, not closing scientific cases alone.
- Output format has two distinct, strictly-named categories. Language around outputs is strict — "watch-list" and "candidate" must never be used interchangeably in reports, UI, dashboard, or external communication.
- PRD §11 review UI has an explicit "PROMOTE TO CANDIDATE" action, only available after external follow-up evidence is attached.
- Success metrics distinguish between watch-list activity (routine pipeline operation) and candidate promotion (rare, significant event).
- If external follow-up is not feasible for a given watch-list entry, it stays watch-list forever — that is acceptable and is not a pipeline failure.

## Alternatives considered

- **Single-stage candidate.** Rejected — scientifically indefensible.
- **Stage A only.** Rejected — conflates real-time flag with closure; no path to defensible discovery claim.
- **Three-stage with intermediate "prospect".** Rejected — adds complexity without resolving the fundamental alert-only limitation; the bright line between alert-only and follow-up-confirmed is what matters.
- **Probabilistic scoring (no discrete stage).** Rejected — harder to audit, harder to pre-register, harder to communicate.

## References

- PRD §5, §11
- Peer-review agent output, 2026-04-22
- Wright et al. 2018, arXiv:1809.06857 (technosignature publishing standards — null-hypothesis-first framing)
