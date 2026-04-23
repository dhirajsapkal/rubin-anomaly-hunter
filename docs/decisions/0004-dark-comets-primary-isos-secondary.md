# ADR-0004 — Dark comets primary target, ISOs secondary

**Status:** Accepted
**Date:** 2026-04-22

## Context

Original framing was ISO-only. Peer review surfaced a physics problem:

- Alert-only short-arc astrometry cannot close e > 1 with small σ. Micheli et al. 2018 needed 818 observations over 80 days to claim 'Oumuamua's hyperbolic nature robustly.
- A typical Rubin 3-night tracklet (4–8 detections) yields σ(e) ≈ 0.3. "Unbound" and "high-e Centaur / Oort returner" do not separate at that precision.
- 3I/ATLAS itself was only confirmed hyperbolic after Rubin + ATLAS + follow-up combined; not from a single-survey alert stream.

Dark comets (Seligman et al. 2023, ApJ 162:229) have a different anomaly signature: non-gravitational acceleration (Marsden A1, A2, A3) without visible coma or tail. This signature resolves from short-arc, alert-only astrometry because the anomaly is quantitative (residuals from orbital fit) rather than morphological (need long light curves or deep imaging). The pipeline feature engineering is ~90% shared between the two targets.

## Decision

Dark comets become the **primary** target. ISOs remain a **secondary** target, delivered as a bonus output of the same pipeline when a tracklet happens to best-fit e > 1 with usable σ(e).

## Consequences

- Pipeline has two watch-lists with distinct criteria but shared feature extraction.
- Expected output distribution: dark-comet watch-list is the continuous primary deliverable; ISO watch-list is a rare bonus. Success metrics and null-field budget reflect this.
- Scientific framing becomes defensible from alert-only data — the primary claim (dark-comet candidate) doesn't depend on the hyperbolic closure problem.
- Any refactor that demotes dark comets or elevates ISOs to primary requires a new ADR and a reassessment of the orbit-closure constraint.

## Alternatives considered

- **ISO-only (original plan).** Rejected — closure infeasible from alert data; project would generate indefensible candidate claims.
- **Dark comets only.** Rejected — ISOs share the pipeline at no extra cost and represent a real scientific opportunity when a hyperbolic fit does emerge.
- **Both equal-priority.** Rejected — clarity of primary output matters for success metrics, null-field budgets, and user expectations about what a "normal run" looks like.
- **Pivot to outer-Solar-System / Sedna-like objects.** Noted as a future sibling target, not taken up now.

## References

- PRD §1, §3, §5
- Seligman et al. 2023, ApJ 162:229 (dark comets as a class)
- Micheli et al. 2018, Nature 559:223 ('Oumuamua astrometry burden)
- Peer-review agent output, 2026-04-22
