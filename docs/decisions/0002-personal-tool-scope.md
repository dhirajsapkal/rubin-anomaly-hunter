# ADR-0002 — Personal tool scope (not OSS, research paper, or service)

**Status:** Accepted
**Date:** 2026-04-22

## Context

Four plausible audiences were considered during plan mode: personal tool, open-source community tool, research-paper support, and real-time alert service. Each implies substantially different engineering investment:

- OSS: docs, CI, packaging, user support, broad platform compatibility
- Research paper: academic collaboration, formal reproducibility, MPC submission mechanics, publication workflow
- Service: uptime, infra, user management, billing, SLA

User context: hobby project, Windows 11, no academic affiliation.

## Decision

Personal-tool scope. Pipeline runs on the user's Windows machine; outputs are notebooks and dashboards the user personally reviews.

## Consequences

- Engineering cost is minimized — no distribution artifacts, no CI obligation, no user-facing reliability commitment.
- No external publication obligation — null results are fine; nobody is waiting on a paper.
- Licensing constraints are softer — `find_orb` personal-use-only (ADR-0008) is tolerable because we never redistribute.
- Any future pivot to OSS, paper support, or service requires revisiting: licensing (especially `find_orb`), reproducibility instrumentation, attribution, secrets handling, and packaging.
- Review UI (Streamlit/Jupyter) is local-only; no public endpoints.

## Alternatives considered

- **Open-source community tool.** Rejected — too much overhead for a hobby project; packaging and docs burden doesn't match the user's goals.
- **Research paper support.** Rejected — requires academic collaboration the user doesn't have; MPC credit mechanics don't support hobbyist solo submissions; paper-grade reproducibility is a much higher bar.
- **Alert service.** Rejected — requires infra and user-facing reliability; orthogonal to the user's real interest in hands-on anomaly hunting.

## References

- PRD §1, §2, §17
- User clarification during plan mode, 2026-04-22 (AskUserQuestion response)
