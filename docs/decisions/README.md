# Architecture Decision Records

Ordered log of substantive decisions made on this project, with reasoning for each. An ADR is immutable after acceptance — if a decision changes, add a new ADR and mark the old one **Superseded**. Never rewrite history.

## Index

| ID | Title | Status | Date |
|----|-------|--------|------|
| [0001](0001-scope-narrowing-uap-to-iso.md) | Scope narrowing: from UAPs to ISO/dark-comet hunting | Accepted | 2026-04-22 |
| [0002](0002-personal-tool-scope.md) | Personal tool scope (not OSS, research paper, or service) | Accepted | 2026-04-22 |
| [0003](0003-rubin-primary-ztf-calibration.md) | Rubin primary, ZTF as calibration rail | Accepted | 2026-04-22 |
| [0004](0004-dark-comets-primary-isos-secondary.md) | Dark comets primary target, ISOs secondary | Accepted | 2026-04-22 |
| [0005](0005-two-stage-gate.md) | Two-stage gate: watch-list → candidate | Accepted | 2026-04-22 |
| [0006](0006-commissioning-window-threshold-lock.md) | Commissioning window + dated threshold lock | Accepted | 2026-04-22 |
| [0007](0007-delegate-tracklet-linking.md) | Delegate tracklet linking to heliolinc3d | Accepted | 2026-04-22 |
| [0008](0008-find-orb-for-orbit-fitting.md) | find_orb for hyperbolic + non-grav orbit fitting | Accepted | 2026-04-22 |
| [0009](0009-own-detection-history-layer.md) | Own detection-history layer | Accepted | 2026-04-22 |
| [0010](0010-alert-only-no-rsp-access.md) | Alert-stream-only access (no RSP/Butler/DP1) | Accepted | 2026-04-22 |
| [0011](0011-mission-control-modern-visual-direction.md) | Mission-Control Modern visual direction (supersedes Observatory Night-Log) | Accepted | 2026-04-22 |
| [0012](0012-narrative-first-information-architecture.md) | Narrative-first IA on Candidate Detail | Accepted | 2026-04-22 |

## Maintenance

See `../../CLAUDE.md` "Decision-record maintenance protocol" section for when and how to add new ADRs.

Template: `template.md`.

## Status values

- **Accepted** — in force, governs current design.
- **Superseded by ADR-NNNN** — replaced by a later ADR; retained for historical record, with forward link.
- **Deprecated** — no longer applicable but not replaced (rare).
- **Proposed** — under discussion, not yet accepted.
