# ADR-0015 — Display typography: IBM Plex Sans, sentence case

**Status:** Accepted
**Date:** 2026-04-23
**Supersedes:** (amends ADR-0011)
**Superseded by:** —

## Context

ADR-0011 set IBM Plex Mono as the display face — used at 48–120 px for
page titles, the Tonight hero numeric, and section headlines — with
`text-transform: lowercase` applied across display elements. This was the
"Mission-Control Modern" direction.

Post-implementation review, the Visual Design audit (2026-04-23) found
that **monospace at display size reads as "terminal cosplay"** on a
hobbyist's personal-tool. The lowercase-forced headings compounded this:
`tonight` set at 48 px mono lowercase communicated "software project with
an attitude" rather than "science desk, quiet night". Combined with the
120 px amber hero numeric (`01`) and a full-width amber mock-mode banner,
the page read as loud ops chrome when the actual content was `"one entry
tonight; alert volume typical."`

The other audits (IA, data-storytelling, interaction) raised different
issues but all noted the visual language was miscalibrated for the
register of the tool.

## Decision

Amend ADR-0011's typography clause as follows:

- **Display face = IBM Plex Sans 500/600, sentence case**, not IBM Plex
  Mono. Applied to the Tonight lede sentence, page-head titles, canvas
  band titles, narrative headlines. Size range
  `clamp(28px, 3.2vw, 44px)` for the lede; 28–32 px for page titles.
  Letter-spacing `-0.02em`, line-height `1.15`.
- **IBM Plex Mono is reserved for data** — identifiers (`wle-0x…`),
  numeric values, timestamps, tabular metrics, small labels with wide
  tracking, code. Never on display-sized prose.
- **Lowercase-forced display is retired.** Sentence case everywhere.
  Existing `text-transform: lowercase` rules on `.rh-page-header .title`
  and the Tonight hero are removed. Uppercase-caps-with-wide-letterspacing
  remains valid only on 10–11 px micro labels (`.data-label`,
  `.canvas-band__eyebrow`).

All other ADR-0011 tokens stay:
- Palette: near-black `#070A10`, surfaces `#10151E` / `#181E2A`, amber
  `#FFB020`, kind colours `#7DD3FC` / `#FF8FA3`, decision palette, health
  palette.
- Invariants: no `backdrop-filter`, no `color-mix()` in production CSS.
- Amber usage discipline *tightens* — amber is now reserved for the
  element currently holding focus or attention (hovered row, active nav
  destination, pending decision, the lede's key phrase). It is no longer
  applied to static chrome.

## Consequences

**New capabilities**
- The lede sentence reads as editorial voice, not code. "One
  short-arc dark-comet candidate tonight — 50 alerts, 48 tracklets
  linked, yield in line with the 14-night median." is now set in Sans,
  sentence case — the correct register for a sentence a human reads.
- Amber regains signal value. When amber appears it means "pay
  attention to this element"; previously it appeared on five ambient
  elements and signified nothing.

**New obligations**
- Any new component that needs display-size text must use
  `var(--font-display)` (now Plex Sans). Mono is only correct for data.
- The `--fs-hero: 7.5rem` token is retired in favour of `--fs-lede:
  clamp(28px, 3.2vw, 44px)`. Code using the old token must migrate.
- `.hero-tonight`, `.hero-numeric`, `.hero-verdict`, `.hero-breakdown`,
  `.mock-banner`, `.lead-story*` classes are removed from theme.css.
  Any caller still referencing them will render unstyled — grep before
  shipping.

## Alternatives considered

- **Keep Plex Mono display, remove lowercase only.** Rejected — the
  visual audit's core finding was that mono-at-display-size reads wrong
  regardless of case.
- **Editorial serif display (GT Sectra / Recoleta).** Rejected — risks
  the "Observatory Night-Log" aesthetic the user already explicitly
  rejected in ADR-0011's ancestry. Plex Sans is the pragmatic middle:
  drops the terminal cosplay, keeps the IBM Plex family coherent.
- **Terminal-dense doubling-down.** Rejected — mathematically the
  product has 0–3 watch-list entries per night, not 200; "more density"
  was the wrong response to "too complicated."

## References

- ADR-0011 (Mission-Control Modern visual direction — partially
  superseded by this ADR's typography clause)
- ADR-0014 (new IA — companion decision)
- 2026-04-23 Visual Design audit (agency specialist); Data-Storytelling
  audit (dissenting but accepted the typography split)
- IBM Plex family: https://www.ibm.com/plex/
