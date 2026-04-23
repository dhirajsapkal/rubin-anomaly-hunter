# ADR-0011 — Mission-Control Modern visual direction

**Status:** Accepted
**Date:** 2026-04-22
**Supersedes:** Visual direction section of `docs/ux/design-system.md` v0.1 ("Observatory Night-Log")

## Context

The initial dashboard shipped with an "Observatory Night-Log" aesthetic — Fraunces serif display, Inter Tight body, warm paper-cream focused-reading surfaces on a deep ink-blue base, phosphor-green accent. The user reviewed the rendered result and rejected it outright ("I don't like the design at all"). Separately, the user reported a "random black square" rendering issue most likely caused by the combination of `backdrop-filter: blur(1px)` + `color-mix()` on `.tile-glass` not rendering reliably inside Streamlit's container DOM.

The user then installed the `frontend-design` skill from Anthropic's claude-code plugin marketplace and asked for a modern redesign. The skill guides toward picking a bold, intentional direction rather than hedged refinement.

## Decision

Replace the Observatory Night-Log direction with **Mission-Control Modern**.

Concrete commits:

- **Typography:** single-family — IBM Plex Mono (display + data) + IBM Plex Sans (body). No serifs. Distinctly technical, unmistakably operational.
- **Palette:** near-black base `#070A10`, single **electric amber** `#FFB020` accent carrying all NEW/active/primary signals. Kind hues: electric sky blue `#7DD3FC` (dark comet) and warm rose `#FF8FA3` (ISO). Decision palette: sharp Tailwind-style hues (`#5EEAD4` / `#FDBA74` / `#F87171` / `#C084FC`).
- **Atmosphere:** subtle layered radial-gradient mesh (amber + cyan + violet, all < 6% alpha) + 4% SVG grain overlay on body.
- **Layout:** dense data-table rows (not cards) for Watch List, 120 px tabular-mono hero numeric on Tonight with soft amber glow, telemetry status bar across the top of pages, sharp 2–6 px radii (no SaaS-soft corners), 1360 px content width.
- **Motion:** staggered entry on page load, pulsing amber dot on NEW pills (2 s cycle), sparklines draw via stroke-dasharray, hero fade-in. All CSS-only. No bouncy easing.

The `.tile-glass` `backdrop-filter` + `color-mix()` combination (root cause of the black-square bug) is eliminated. Surfaces now use plain rgba values and top-light linear gradients.

## Consequences

- `dashboard/static/theme.css` and `dashboard/lib/theme.py` `_STREAMLIT_OVERRIDES` were rewritten wholesale to match the new direction.
- `docs/ux/design-system.md` v0.1 is partially superseded — its §§1–3 (aesthetic statement, typography, color tokens) no longer match the implementation. The sections on information architecture, language rules, anti-patterns (§§4–8) remain in force.
- The invariants from ADR-0005 (watch-list ≠ candidate, "discovery" banned) are preserved unchanged.
- `docs/ux/brief.md` persona, JTBD, and IA sections remain authoritative.
- Future direction changes require a new ADR. No edit-in-place of `theme.css` for aesthetic drift.

## Alternatives considered

- **Keep Observatory Night-Log, polish harder.** Rejected — user feedback was direction, not polish.
- **Brutalist / terminal retrofuturism.** Rejected as too costumed — risks reading as sci-fi cosplay.
- **Editorial / science-magazine maximalism.** Rejected as too loud for a quiet daily-review tool.
- **Frosted visionOS / Apple-current.** Rejected as trendy and less distinctive.
- **Bloomberg-terminal cold.** Rejected — would lose the curious-hobbyist register entirely.

## References

- PRD.md §11
- docs/ux/brief.md (persona, IA — preserved)
- docs/ux/design-system.md (partially superseded by this ADR)
- Anthropic `frontend-design` skill (https://github.com/anthropics/claude-code/tree/main/plugins/frontend-design)
- User session 2026-04-22
