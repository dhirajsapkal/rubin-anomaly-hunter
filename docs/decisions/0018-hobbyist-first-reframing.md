# ADR-0018 — Hobbyist-first reframing of the single-surface IA (amends ADR-0014)

**Status:** Accepted
**Date:** 2026-04-24
**Supersedes:** —
**Superseded by:** —
**Amends:** ADR-0014

## Context

Real deployment against the demo DB (2026-04-24) exposed a UX gap that the
four-agent audit behind ADR-0014 did not surface: the information
architecture is *correct* (single-surface, master-detail, URL-addressable),
but the **copy and framing read as a specialist science dashboard**, not a
tool for the project's actual operator. The owner described himself as
"an amateur hobbyist" and said, reasonably: "right now there's no data so
there's literally nothing to do on the app."

Two contributing problems:

1. **Jargon in the chrome.** The primary surface talks about the
   *commissioning window*, *σ(e)*, *threshold-lock*, *Marsden A1/A2/A3*.
   Without domain context, every panel reads as "wait for someone else to
   explain what this means" — and an empty watch-list reads as "nothing
   happened" instead of "the pipeline is working; this is what a quiet
   night looks like."

2. **No affordance for what the operator actually wants to do.** The
   operator's stated goal is: *"see what interesting data the telescope
   is getting, have the app explain it, and track objects that are moving
   weirdly. If the pipeline finds something new, advise me on how to
   report it."* The existing design supports the first two needs
   partially and the third not at all — Ledger records past decisions
   but does not guide new ones.

A related scope conversation during the session confirmed that **UAP /
earth-orbit unknown objects are physically out of reach via Rubin**
(focus at infinity, ~30s exposures while slewing; close-to-Earth objects
smear into streaks and are filtered upstream before alerts are ever
issued — see PRD §10 N4, Tyson et al. 2020). ADR-0001 already scopes
this out; this ADR reaffirms it so future design drift toward "UAP
detector" framing has a breadcrumb to check against.

## Decision

Keep ADR-0014's single-surface master-detail architecture. **Reframe the
copy, affordances, and secondary destinations for a hobbyist audience**
along three plain-English panels on the primary surface:

1. **"What the telescope saw tonight"** — a wide sky map (Mollweide
   kept), one-sentence totals in plain English ("Rubin imaged ~670k
   objects tonight. Most are known asteroids. 5 look weird enough to
   watch"), and a short *what's worth knowing* explainer (two lines, not
   a science essay).

2. **"Weird things we're watching"** — the existing master-detail band,
   but every entry is rewritten in plain language. Jargon is translated,
   not hidden: "σ(e) = 0.08" becomes "confidence: medium"; "Marsden A1
   = 1.4×10⁻⁸ AU/d²" becomes "this rock is being pushed by something
   invisible — about the strength a comet's outgassing would cause, but
   it shows no coma." The ADR-0012 reading order (narrative → why →
   evidence) is preserved inside the canvas.

3. **"What to do with this flag"** — a new canvas band per entry, only
   visible when an entry is selected. Concrete, plain-language
   guidance on taking a flag from watch-list toward a possible
   discovery. See **Consequences → New capabilities** for the exact
   content; see **Consequences → Invariants preserved** for how this
   stays on the right side of ADR-0005.

Secondary destinations are simplified:

- **Ledger** → renamed **"Past flags"** and rewritten in plain English
  ("You accepted 3 dark-comet flags, rejected 3, and promoted 1 to
  candidate since 2026-04-01"). Retained — the audit trail is still
  real, just framed for a human not a log reader.
- **Health** → folded into the top nav strip as provenance chips
  (already present). The separate Health page is retired; operators
  who want the metrics table can re-open it via a small "show
  pipeline details" expander on the Past-flags page. Zero loss of
  information; significant reduction in perceived surface area.

## Consequences

### New capabilities

- **Per-entry reporting guidance** (Panel 3 body). For each selected
  watch-list entry, render four short sections in plain English:

  | Section | Content |
  |---|---|
  | **Why this might be new** | "No known object within 30 arcminutes in MPC's catalogue" + linking-first date ("your pipeline first connected these detections on YYYY-MM-DD"). |
  | **What would make it real** | One-line plain-English restatement of the two-stage gate: "a new Solar System object needs a second observatory to independently see it before it counts as a discovery. Until then, this is a watchlist flag, not a confirmed find." |
  | **How to get eyes on it** | Concrete links + a pre-formatted coordinates-and-epoch block the operator can paste: MPC NEO Confirmation Page (near-Earth cases), ATel (public announcements), amateur networks (BAA Comet Section for sustained follow-up). |
  | **What credit looks like** | Honest note: "MPC discovery credit goes to Rubin and the observatory that does the follow-up, not to this pipeline. But connecting these detections first matters — it's how follow-up starts." |

- **Plain-language translation layer**. A small helper module
  (`dashboard/lib/plainlang.py`) that maps quantitative fit values to
  hobbyist-readable phrases:

  | Quantitative input | Plain-language output |
  |---|---|
  | σ(e) < 0.05 | "high confidence" |
  | 0.05 ≤ σ(e) ≤ 0.15 | "medium confidence" |
  | σ(e) > 0.15 | "low confidence — this might just be noise" |
  | e > 1, σ(e) < 0.15 | "the orbit's shape suggests it came from outside the Solar System" |
  | |A1/A2/A3| > threshold, PSF-consistent | "being pushed by something invisible, but we can't see a comet's tail" |

  Used by Panel 2 entry cards and Panel 3 "why this might be new."

- **Pre-discovery attribution**. Every watch-list entry carries a
  "linking-first" timestamp (pipeline's first link of its detections
  into one tracklet). This is shown as "you spotted this on
  YYYY-MM-DD" — a lightweight hint of pre-catalogue priority, not a
  credit claim. No schema change required: already derivable from
  `tracklets.created_utc`.

### New obligations

- **Scientific language discipline (ADR-0005) must survive the
  translation.** Panel 2 and Panel 3 may use "weird," "moving weirdly,"
  "looks new" — but must never use "candidate," "confirmed,"
  "discovery," or "first detection of X" for watch-list entries. The
  plain-language layer explicitly translates *toward* hedged
  confidence ("this might be new," "this looks like"), never toward
  claims. Unit tests on `plainlang.py` assert this.

- **Reporting guidance must not suggest public claims.** Panel 3 lists
  MPC NEO Confirmation and ATel as *follow-up-request* channels, not
  announcement channels. Copy explicitly says: "Don't post this on
  social media as a discovery — it isn't one yet." This is a
  reputation-hygiene invariant.

- **Retired code.** The current `dashboard/app.py` copy is rewritten
  in place. `dashboard/pages/2_Health.py` is removed (metrics fold
  into the top chip + a Past-flags expander). The file-rename
  `1_Ledger.py` → `1_Past_flags.py` follows Streamlit's multipage
  convention (number prefix drives order). Retired files: none from
  ADR-0014's set; the IA structure itself doesn't move.

### Invariants preserved

- **ADR-0001 (scope narrowing: UAP → ISO/dark-comet)** — explicitly
  reaffirmed. The hobbyist copy uses words like *weird* and *unknown
  object* but never *UAP* or *UFO*. If a future session drifts toward
  UAP framing, this ADR is the breadcrumb that catches it.
- **ADR-0004 (dark comets primary, ISOs secondary)** — unchanged.
- **ADR-0005 (two-stage gate)** — preserved in both spirit and text.
  Panel 3's "what would make it real" is literally a plain-English
  restatement of the alert-only-is-watch-list-not-candidate rule.
- **ADR-0011 (Mission-Control Modern visual direction)** — palette,
  typography, no-backdrop-filter rules unchanged. Only the **copy**
  changes, not the chrome.
- **ADR-0012 (narrative-first reading order inside the canvas)** —
  preserved, with Panel 3 appended as the last canvas band.
- **ADR-0014 (single-surface master-detail IA)** — structure preserved.
  This ADR adds copy, one helper module, and one canvas band.
- **PRD §1 honest scope statement** — Panel 3's "what credit looks
  like" is a direct gloss of PRD §1's MPC-credit paragraph.

## Alternatives considered

- **Add a "simple mode" toggle alongside the existing science mode.**
  Rejected — doubles UX maintenance for a one-operator tool, and risks
  the simple mode silently drifting into a stale fork.
- **Expand scope to UAP / earth-orbit unknowns.** Rejected — blocked by
  Rubin's optics (focus at infinity, fast slew) and by the upstream
  streak-filtering in the alert pipeline itself. Would produce an empty
  feed indefinitely; no amount of UX can rescue a data source that
  doesn't exist.
- **Commissioning-progress dashboard as the primary surface.** Considered
  earlier in the design conversation; rejected because it solves the
  "empty nights feel dead" problem with the same science-jargon audience
  that caused the problem in the first place.
- **"Hero object of the night" ranking** (surface the most-interesting
  tracklet even if not flagged). **Held as a follow-up.** If Panel 1
  feels too sparse after the reframing ships, a small "most unusual
  tracklet tonight" affordance at the top of Panel 2 is a natural
  addition. Not in this ADR's scope because it needs a ranking function
  (on what? |A1|? σ(e)? a blended score?) that deserves its own ADR.

## Wireframe

```
┌──────────────────────────────────────────────────────────────────────────┐
│ RUBIN · tonight  ·  past flags           data: fink · orbits: mock       │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Rubin imaged ~670k objects tonight. Most are known asteroids. 5 look    │
│  weird enough to watch. Fri 2026-04-24 · updated 17:05.                  │
│                                                                          │
│  ┌────────────────────────────────────────────────────┐                  │
│  │            Mollweide sky · 1000 detections         │  What's worth    │
│  │                   amber rings = flagged            │  knowing         │
│  │                                                    │  ─────────────   │
│  │             · · ·      · · · · ·    · ·            │  Most moving     │
│  │          · ○ · · ·  · · · · ·   · · · · ·          │  dots here are   │
│  │            · · · · · · · · · · · ·  · ·            │  known rocks.    │
│  │                                                    │  The pipeline    │
│  │                                                    │  is watching     │
│  │                                                    │  for ones whose  │
│  │                                                    │  motion doesn't  │
│  │                                                    │  match any       │
│  │                                                    │  known one.      │
│  └────────────────────────────────────────────────────┘                  │
│                                                                          │
│  ── Weird things we're watching ──────────────────────────────────────   │
│                                                                          │
│  ┌──────────────────────┐  ┌─────────────────────────────────────────┐   │
│  │ wle-0x00000004       │  │ wle-0x00000004 · dark-comet-like        │   │
│  │ DARK-COMET           │  │ First connected 2026-04-20, 7 nights.   │   │
│  │ 2026-04-20 · NEW     │  │                                         │   │
│  ├──────────────────────┤  │ What we saw                             │   │
│  │ wle-0x00000003       │  │ A rock-looking body that's accelerating │   │
│  │ DARK-COMET           │  │ in a direction gravity can't account    │   │
│  │ 2026-04-18 · NEW     │  │ for — about the strength a comet's     │   │
│  ├──────────────────────┤  │ outgassing would cause — but we see no  │   │
│  │ wle-0x00000005       │  │ tail or coma. Confidence: medium.       │   │
│  │ ISO-SHAPE            │  │                                         │   │
│  │ 2026-04-17 · NEW     │  │ Hypotheses                              │   │
│  ├──────────────────────┤  │ □ Normal comet, coma too faint to see   │   │
│  │ wle-0x00000002       │  │ □ Dust artifact, orbit fit noise        │   │
│  │ DARK-COMET           │  │ ✓ Genuine non-grav body (dark comet)    │   │
│  │ 2026-04-13 · NEW     │  │                                         │   │
│  ├──────────────────────┤  │ Evidence (orbit fit, cutouts)  ▸        │   │
│  │ wle-0x00000001       │  │                                         │   │
│  │ DARK-COMET           │  │ ── What to do with this flag ──         │   │
│  │ 2026-04-09 · NEW     │  │                                         │   │
│  └──────────────────────┘  │ Why this might be new                   │   │
│                            │ No match within 30' in MPC's catalogue. │   │
│                            │ Your pipeline first connected these     │   │
│                            │ 7 detections on 2026-04-20 17:14 UTC.   │   │
│                            │                                         │   │
│                            │ What would make it real                 │   │
│                            │ A new Solar System object needs another │   │
│                            │ observatory to see it independently.    │   │
│                            │ Until then this is a flag, not a find.  │   │
│                            │                                         │   │
│                            │ How to get eyes on it                   │   │
│                            │ • MPC NEO Confirmation Page (near-Earth)│   │
│                            │ • ATel (public request for follow-up)   │   │
│                            │ • BAA Comet Section (amateur follow-up) │   │
│                            │                                         │   │
│                            │ [Copy coords + epoch to clipboard]      │   │
│                            │                                         │   │
│                            │ What credit looks like                  │   │
│                            │ Discovery credit goes to Rubin + the    │   │
│                            │ observatory that does the follow-up.    │   │
│                            │ But connecting these detections first   │   │
│                            │ matters — it's how follow-up starts.    │   │
│                            │                                         │   │
│                            │ Don't post this as a discovery on       │   │
│                            │ social media. It isn't one yet.         │   │
│                            └─────────────────────────────────────────┘   │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

## References

- PRD §1 (honest scope statement — credit model, hobbyist framing)
- PRD §10 N4 (satellite streaks are null hypothesis, not signal)
- PRD §11 (outputs and review UX — "No promotions is a successful day")
- PRD §17 (out of scope — UAP explicitly excluded)
- ADR-0001 (scope narrowing: UAPs → ISO/dark-comet hunting) — reaffirmed
- ADR-0004 (dark comets primary, ISOs secondary)
- ADR-0005 (two-stage gate: watch-list ≠ candidate)
- ADR-0011 (Mission-Control Modern visual direction)
- ADR-0012 (narrative-first reading order — preserved in canvas)
- ADR-0014 (single-surface master-detail IA) — this ADR amends
- Tyson et al. 2020, AJ 160 — LSST satellite streak mitigation (why UAP/earth-orbit is data-blocked)
