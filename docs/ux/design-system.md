# Rubin Anomaly Hunter — Design System

**Version:** 0.1
**Companion:** `docs/ux/brief.md` (UX), `dashboard/static/theme.css` (implementation)
**Framework target:** Streamlit v1.33+ with `st.markdown(..., unsafe_allow_html=True)`
**Date:** 2026-04-22

---

## 1. Aesthetic statement

**Direction: "Observatory Night-Log."**

The dashboard is a late-night observing journal kept under lamplight, not a SaaS control panel. Deep ink-blue backgrounds — the color of a midnight sky past civil twilight — hold the whole app. Content surfaces are a warm paper-cream, pulled back and slightly desaturated so long reading sessions in a dark room don't burn retinas. Headings are set in a hand-cut display serif with the character of a 1950s observatory logbook cover; body copy is a humanist serif or well-drawn sans with restrained warmth; every number — MJD, orbital element, flux, arcmin — is set in a crisp monospace, because this tool lives or dies on numeric trust.

A single phosphor-green accent (`#B9F15D`) carries all activation, selection, and "new" signals. Semantic colors for the four decision actions (Accept / Defer / Reject / Promote) are each distinct hues that never collapse to red/green alone. The whole composition favors asymmetric columns, generous margin on the outside of the grid, and a faint SVG-generated noise texture on the deep background — atmosphere, not spectacle. No gradients on surfaces. No stock photos. No emoji. If a visitor glances over Dhiraj's shoulder and thinks *"is that an old astronomy notebook?"* — we got it right.

---

## 2. Typography

### 2.1 Typeface picks

Three roles: **display**, **body**, **mono**. Two options per role so the implementer can fall back on availability. Final choice listed **first**; alternates listed after.

| Role | Primary (ship this) | Fallback A | Fallback B |
|------|---------------------|-----------|-----------|
| **Display** (page titles, empty-state verdict, big numbers) | **Fraunces** (Google Fonts — variable, SIL OFL) | **IBM Plex Serif** (Google Fonts, SIL OFL) | **GT Sectra** (commercial — only if the user has a license) |
| **Body** (paragraphs, row text, button labels) | **Inter Tight** (Google Fonts, SIL OFL) — chosen over plain Inter for tighter metrics on dense data UIs | **Space Grotesk** (Google Fonts, SIL OFL) | **Geist** (self-hosted via @font-face, SIL OFL) |
| **Mono** (all data readouts, IDs, MJD, orbital elements, diffs, provenance) | **JetBrains Mono** (Google Fonts, SIL OFL) | **IBM Plex Mono** (Google Fonts, SIL OFL) | **Space Mono** (Google Fonts, SIL OFL) |

**Why Fraunces as display:** it is a modern high-contrast serif with optional "SOFT" and "WONK" axes. At the default setting it reads as a dignified book face; pushed slightly toward soft it gets a warm, hand-drawn quality appropriate to a hand-bound journal. Variable axes mean we can use a single font file for weights 400–900 and keep load light.

**Why Inter Tight as body over Inter:** Inter is the SaaS-default the brief explicitly tells us to avoid. Inter Tight has tighter default tracking and a slightly more humanist tone at small sizes, so it pairs with Fraunces without fighting it. If the implementer prefers more character, swap to Space Grotesk — it is the more distinctive option.

**Why JetBrains Mono:** its digit forms are unambiguous (clear `0` vs. `O`, clear `1` vs. `l`), it has a tasteful ligature set that can be turned on or off, and it is near-universally available via Google Fonts' stable CDN.

### 2.2 Google Fonts @import (single line, what the CSS actually uses)

```
https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght,SOFT@9..144,400;9..144,500;9..144,700;9..144,900&family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap
```

### 2.3 Type scale

Opinionated modular-ish scale, not strict ratio. All sizes in rem (root = 16px).

| Token | rem | px | Role |
|-------|-----|----|------|
| `--fs-display-xl` | 3.25 | 52 | Tonight empty-state verdict only |
| `--fs-display-lg` | 2.25 | 36 | Page titles (Fraunces, weight 500) |
| `--fs-display-md` | 1.625 | 26 | Card titles, section headings |
| `--fs-body-lg` | 1.125 | 18 | Lead paragraphs, one-line verdicts |
| `--fs-body` | 1.0 | 16 | Default body |
| `--fs-body-sm` | 0.875 | 14 | Secondary copy, metadata labels |
| `--fs-mono` | 0.9375 | 15 | Inline mono in prose |
| `--fs-mono-sm` | 0.8125 | 13 | Dense monospace blocks (orbit fit, provenance) |
| `--fs-micro` | 0.75 | 12 | Badges, status pills, chart legends |

**Line heights:** 1.2 for display, 1.5 for body, 1.45 for mono blocks.

**Weights in use:** Fraunces 500 (titles) and 700 (big verdict). Inter Tight 400 (body), 500 (labels), 600 (button text). JetBrains Mono 400 (default) and 500 (emphasized data).

---

## 3. Color tokens

Dark mode only. Every color has a CSS variable and a specific hex. Each token below appears verbatim in `dashboard/static/theme.css`.

### 3.1 Background / surface

| Token | Hex | Role |
|-------|-----|------|
| `--bg-deep` | `#0B1020` | App background. Deep ink; very slight blue bias. Carries the noise texture. |
| `--bg-elevated` | `#131A2E` | Secondary panels, sidebar rail. |
| `--surface-paper` | `#F2E8D5` | Focused-reading surfaces — Candidate Detail card, Archive row expansion. A warm paper-cream. Body text on this surface uses `--ink-on-paper`. |
| `--surface-card` | `#1A2340` | Default card surface on the deep background (Tonight tiles, watch-list rows). |
| `--surface-card-hover` | `#1F2A4D` | Hover / focus state for interactive cards. |
| `--divider` | `#2A3458` | 1px rules, card borders on dark surfaces. |
| `--divider-paper` | `#D4C9B0` | Rules on the paper surface. |

### 3.2 Text

| Token | Hex | Role |
|-------|-----|------|
| `--text-primary` | `#EDE6D3` | Primary copy on dark surfaces. A warm off-white — never pure `#FFF`. |
| `--text-secondary` | `#A9B1C6` | Metadata, row secondary, captions on dark. |
| `--text-tertiary` | `#6D7595` | De-emphasized labels, timestamps on dark. |
| `--ink-on-paper` | `#1A1A2E` | Primary text on the paper surface. Near-black with a hint of blue so it reads as ink, not print. |
| `--ink-on-paper-muted` | `#555770` | Secondary ink on paper. |

### 3.3 Accent (single bright)

| Token | Hex | Role |
|-------|-----|------|
| `--accent-phosphor` | `#B9F15D` | The one bright accent. Used for: new-since-last-visit dot, active nav item, focused input ring, keyboard-focus outline, the sparkline stroke on Tonight. Used sparingly — if it's on more than ~5% of the viewport at once, something is wrong. |
| `--accent-phosphor-dim` | `#6B8C37` | Muted variant for hover-out states and secondary ticks. |

### 3.4 Semantic — the four decision actions

Each decision action gets a distinct hue. They are never collapsed to red/green alone.

| Token | Hex | Role |
|-------|-----|------|
| `--decision-accept` | `#7FB88F` | Accept. Muted jade — affirmation without celebration. |
| `--decision-defer` | `#D9B06C` | Defer. Warm amber — "come back to this". Deliberately the visually softest of the four so defer feels low-cost. |
| `--decision-reject` | `#C26B6B` | Reject. Desaturated rust — a no, not an emergency. Never pure red (PRD §1 — we are not a UAP/UFO alarm). |
| `--decision-promote` | `#7BA9D9` | Promote to candidate. Cool dusty blue — formal, archival, rare. |

### 3.5 Watch-list category hues

Two distinct hues, both readable against the dark surface and the paper surface. Used on kind badges, tab underlines, chart series, orbit-plot path stroke.

| Token | Hex | Role |
|-------|-----|------|
| `--kind-dark-comet` | `#C88BD0` | Dark-comet watch list. A dusty violet — primary category per ADR-0004, but visually restrained because most entries are dark comets and we don't want to shout. |
| `--kind-iso` | `#E8A87C` | ISO watch list. Warm terracotta — rare (1–10/year per PRD §3), so the hue is a little warmer and more conspicuous than the dark-comet hue. |

### 3.6 Pipeline-health status

Traffic-light-free. Uses shape + color together (see anti-patterns).

| Token | Hex | Role |
|-------|-----|------|
| `--health-ok` | `#7FB88F` | Healthy (same jade as Accept — intentional semantic echo). |
| `--health-warn` | `#D9B06C` | Warning — lag elevated, re-query needed. Same amber as Defer. |
| `--health-stale` | `#8C95B0` | Stale — hasn't run recently. Not an error, just cold. |
| `--health-error` | `#C26B6B` | Error — pipeline stage failed. Same rust as Reject. |

Reusing the decision hues for health is deliberate: the user only has to learn four colors across the whole product.

---

## 4. Spacing scale

Opinionated 4-based scale. All components compose from these exact values; no ad-hoc pixel values in the CSS.

| Token | px | Typical use |
|-------|----|------------|
| `--sp-1` | 4 | Tight inline gaps (between badge and label) |
| `--sp-2` | 8 | Compact vertical rhythm in dense tables |
| `--sp-3` | 12 | Default gap between adjacent form controls |
| `--sp-4` | 16 | Card padding on compact surfaces |
| `--sp-5` | 24 | Card padding default, paragraph spacing |
| `--sp-6` | 32 | Section spacing within a page |
| `--sp-7` | 48 | Between major page sections |
| `--sp-8` | 64 | Page top/bottom margin on large screens |

Border radius: `--radius-sm` = 4px, `--radius-md` = 8px, `--radius-lg` = 14px (cards on paper surface — slightly more generous, feels like a softened notebook corner). No pill-fully-round radii except on status pills (`--radius-pill` = 999px).

---

## 5. Layout primitives

### 5.1 Grid

- **App shell:** fixed left nav rail (224px wide) + fluid main column.
- **Main column max width:** 1200px on Tonight / Watch List / Archive / Pipeline Health. 1040px on Candidate Detail (narrower — focused reading).
- **Minimum supported viewport width:** 1280px (UX brief §7 — desktop only).
- **Page outer gutter:** `--sp-7` (48px) left and right within the main column, `--sp-8` (64px) top, `--sp-7` bottom.
- **Internal column grid:** 12-col flex with `--sp-5` gutters. Asymmetric layouts welcome — see Candidate Detail, where the cutout strip occupies 8 cols and metadata sits in a 4-col sidebar, with the sidebar allowed to hang 12px outside the strict column line (gentle grid-break on purpose).

### 5.2 Content width classes

| Class | max-width | Use |
|-------|-----------|-----|
| `.content-wide` | 1200px | Default |
| `.content-narrow` | 1040px | Candidate Detail |
| `.content-prose` | 680px | Empty-state centered blocks, archive-row expanded note text |

### 5.3 Card patterns

- **Dark card** (`.card-dark`): default. `--surface-card` background, 1px `--divider` border, `--radius-md` corners, `--sp-5` padding.
- **Paper card** (`.card-paper`): Candidate Detail body. `--surface-paper` background, 1px `--divider-paper` border, `--radius-lg` corners, inner shadow `inset 0 1px 0 rgba(255,255,255,0.5)` to give a subtle top-light suggestion (paper is thick, lit from above). `--sp-6` padding.
- **Glass tile** (`.tile-glass`): Tonight summary tiles. `--surface-card` at 60% alpha over the noise texture, 1px `--divider` at 40% alpha. Gives a layered observatory-instrument feel without literal glassmorphism blur.

### 5.4 Noise texture

A subtle SVG-based noise pattern lives on `--bg-deep`, implemented in CSS via a data-URI SVG `<filter type="fractalNoise">`. Opacity 0.035. It should be imperceptible as texture but perceptible as *not flat* — the same way a 16th-century star chart's vellum isn't flat. Implementation details in `theme.css` §noise.

---

## 6. Component inventory (ASCII sketches)

Mini-sketches are illustrative, not pixel-perfect. Implementer uses them to verify structural intent.

### 6.1 Page header

```
┌────────────────────────────────────────────────────────────────────┐
│  TONIGHT                                      Thu 2026-05-14 · 22:47 │
│  ───────                                     commissioning · v0.1    │
└────────────────────────────────────────────────────────────────────┘
```

- Page title in Fraunces 500, 36px, `--text-primary`.
- Short underline bar in `--accent-phosphor`, 48px wide, 2px tall, left-aligned below the title.
- Right-aligned metadata stack in JetBrains Mono 13px: local datetime on top, pipeline-window + config version tag beneath in `--text-tertiary`.
- `--sp-6` below before first content section.

### 6.2 Page nav (left rail)

```
┌──────────────┐
│   RUBIN      │  ← wordmark, Fraunces 500, 18px
│   night-log  │  ← subtitle, Inter Tight italic 13px, --text-tertiary
│              │
│  ● Tonight   │  ← active: phosphor dot + paper-cream text
│    Watch     │  ← inactive: --text-secondary
│    Archive   │
│    Health    │
│              │
│  ─────────   │  ← --divider
│  commissio-  │
│  ning window │  ← --text-tertiary, mono 12px
│  v0.1        │
└──────────────┘
```

- Fixed 224px width. `--bg-elevated` background.
- Wordmark and subtitle top, `--sp-7` from top.
- Nav items stacked, `--sp-3` vertical gap, left-aligned, uppercase not used (reads quieter).
- Active state: a `--accent-phosphor` filled dot (6px) precedes the label + label is `--text-primary`; background unchanged.
- Hover on inactive: label becomes `--text-primary`, no background flash.
- Pipeline-window footer lives at the bottom of the rail, bottom-aligned, `--sp-5` from bottom. This is load-bearing context per ADR-0006.

### 6.3 Summary tile (Tonight)

```
┌───────────────────────────────┐
│  NEW WATCH-LIST ENTRIES       │  ← label, mono 12px, --text-tertiary
│                               │
│   2                           │  ← Fraunces 700, 52px, --accent-phosphor
│   ───                         │  ← 24px phosphor underline
│                               │
│   1 dark comet · 1 ISO        │  ← 14px Inter Tight, --text-secondary
└───────────────────────────────┘
```

- `.tile-glass` pattern (§5.3).
- Two tiles per row on Tonight (new watch-list / alerts ingested) plus a third wider tile for the "last run" sparkline.
- Zero-state: the big number renders `0` in `--text-secondary`, no phosphor underline, secondary line reads `"nothing new since last visit"` in italic.

### 6.4 Watch-list row

```
┌───────────────────────────────────────────────────────────────────┐
│ ●  DARK COMET   wle-0x1a2b3c4d    2026-05-12   7 det / 4n   MPC:— │
│                                                          R: 0.91  │
└───────────────────────────────────────────────────────────────────┘
   ↑       ↑            ↑              ↑           ↑         ↑
   kind    kind badge   internal ID    first-seen  arc       R-score
   dot                  (mono)         (mono)      (mono)    (mono)
```

- `.card-dark`, 64px tall, full-width within main column.
- Leftmost 6px kind dot, either `--kind-dark-comet` or `--kind-iso`, vertically centered.
- Kind badge (text): 11px uppercase JetBrains Mono 500, letter-spacing 0.08em, `--text-secondary`.
- Internal ID: mono, `--text-primary`. Clickable (opens Candidate Detail).
- Metadata fields: each in its own right-aligned fixed-width slot.
- MPC column: `—` (em-dash) if no match, or `known: (xxxxx)` with the matched designation if positive — positive match pushes the row to an amber left border (`--decision-defer`) and de-emphasizes the ID (auto-screenable for rejection).
- Hover: `--surface-card-hover` background, 1px `--accent-phosphor` left border appears (2px wide).
- Focus (keyboard): same as hover plus a 2px `--accent-phosphor` ring offset 2px.

### 6.5 Candidate card (Candidate Detail — paper surface)

```
╔═════════════════════════════════════════════════════════════════════╗
║  [DARK COMET]   wle-0x1a2b3c4d                      MJD 60832.41   ║
║  ───                                                 thresholds-v1 ║
║                                                                     ║
║  NULL-HYPOTHESIS TESTS                                              ║
║  ✓ no MPC match within 30'                                          ║
║  ✓ no streak / streak-adjacent                                      ║
║  ✓ R-score 0.91 > R_min (commissioning)                             ║
║  ✓ morphology PSF-consistent (no coma)                              ║
║  ✓ tracklet quality: nominal                                        ║
║  ○ instrument systematic: not yet checked                           ║
║  ✓ broker-flag drift: none since ingest                             ║
║                                                                     ║
║  ────────────────────────────────────────────────                   ║
║                                                                     ║
║  ORBIT FIT (find_orb, Marsden A1/A2/A3)                             ║
║    a = 3.24 ± 0.12 AU      e = 0.41 ± 0.03                          ║
║    i = 8.2° ± 0.4°         q = 1.91 AU                              ║
║    A1 = 1.4e-8 ± 2e-9 AU/d²                                         ║
║    A2 = 3.0e-10 ± 1e-10                                             ║
║    A3 = 1.1e-10 ± 4e-11                                             ║
║                                                                     ║
║  ──── cutouts (7 epochs) ──────── light curve ──── orbit ──────     ║
║  [ science │ template │ diff  ]   [sparkline]    [ellipse]          ║
║  [ science │ template │ diff  ]                                     ║
║  …                                                                  ║
║                                                                     ║
║  Cross-broker: Fink ✓   Lasair ✓   ALeRCE ∅                         ║
║  Notes: ________________________________________________            ║
║                                                                     ║
║  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────────┐       ║
║  │  ACCEPT  │ │  DEFER   │ │  REJECT  │ │ PROMOTE TO        │       ║
║  │          │ │          │ │          │ │ CANDIDATE         │       ║
║  └──────────┘ └──────────┘ └──────────┘ └───────────────────┘       ║
╚═════════════════════════════════════════════════════════════════════╝
```

- `.card-paper` surface (`--surface-paper`), all text is `--ink-on-paper`.
- Kind badge at top-left is a small inline pill (`.pill-kind-dark-comet` or `.pill-kind-iso`).
- Null-hypothesis test list: monospace. `✓` in `--decision-accept` ink, `✗` in `--decision-reject` ink, `○` (circle) in `--ink-on-paper-muted` for "not yet checked".
- Orbit fit block: monospace, aligned by `=` signs using a 2-col flex — not by spaces.
- Decision action bar: sticky at the bottom of the card (position:sticky, bottom:0), with a soft top shadow on the card indicating scrollable content behind.

### 6.6 Orbit visualization frame

```
  ┌─ orbit (ecliptic, top-down) ───────────────── 2026-05-14 ─┐
  │                                                           │
  │             · Jupiter                                     │
  │                                                           │
  │         ╭─── fit orbit ───╮                               │
  │        ·                   ·                              │
  │       ·      · Mars         ·                             │
  │      ·     · Earth           ·                            │
  │      ·    · Venus             ·                           │
  │       ·    · Sun              ·                           │
  │        ·                    ·                             │
  │         ·                 ·                               │
  │           ╰───── · ──────╯  ← current position            │
  │                  ·                                        │
  │                                                           │
  │  a=3.24  e=0.41  i=8.2°                                   │
  └───────────────────────────────────────────────────────────┘
```

- Dashed thin rule frame, top-left legend label in 12px mono, top-right date in 12px mono, both `--ink-on-paper-muted`.
- Fit orbit stroke: 1.5px, color `--kind-dark-comet` or `--kind-iso` depending on entry.
- Current position: 4px filled dot, color `--accent-phosphor`.
- Reference planets: 2px filled dots, `--ink-on-paper-muted`, labeled in mono italic 11px.
- Orbit caption (a / e / i) bottom-left in mono 12px `--ink-on-paper`.
- Generated by matplotlib into SVG and embedded — do not attempt to render this in pure CSS. The frame (border + captions) is HTML; the ellipse is an SVG child.

### 6.7 Cutout thumbnail

```
 ┌──────────────────────────┐
 │                          │
 │   [ 63×63 diff image ]   │
 │                          │
 ├──────────────────────────┤
 │ diff · MJD 60832.41 · r  │
 └──────────────────────────┘
```

- Fixed 120px × 140px (image area 120×120, caption strip 20px).
- 1px `--divider-paper` border.
- Caption in mono 11px: image type (science / template / diff), MJD, filter band.
- On hover: enlarges in place to 240×280 (CSS `scale(2)` with transform-origin set so it grows away from the neighboring thumbnail, not toward it). No modal, no lightbox — PRD §11 preserves fast review.

### 6.8 Light-curve frame

```
  ┌─ light curve (r + g) ─────────────────────────────────────┐
  │    ·                                                       │
  │       ·       ·                                            │
  │         ·                                                  │
  │                 ·       ·                                  │
  │                    · ·     ·                               │
  │                                                            │
  │  MJD 60828      60830      60832                           │
  └────────────────────────────────────────────────────────────┘
```

- Matplotlib SVG embedded, framed like §6.6 with caption in 12px mono.
- Point markers: `r` band uses a filled circle in `--kind-iso` hue (reused as a neutral warm tone in this chart context); `g` band uses an open circle in `--accent-phosphor-dim`. Band legend in caption.
- Error bars rendered as 1px strokes, no end caps.

### 6.9 Decision action bar

```
 ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────────────┐
 │  ACCEPT  │ │  DEFER   │ │  REJECT  │ │ PROMOTE TO CANDIDATE│
 └──────────┘ └──────────┘ └──────────┘ └─────────────────────┘
```

- Each button is a flat-filled rounded-rectangle (`--radius-md`), 44px tall, padding `--sp-5` horizontal.
- Text: Inter Tight 600, 14px, uppercase, letter-spacing 0.08em.
- Colors (background / text):
  - Accept: `--decision-accept` / `--ink-on-paper`
  - Defer: transparent / `--decision-defer`, 1.5px `--decision-defer` border (defer is the most common action and is styled as the "quiet default" — not filled, to signal low commitment).
  - Reject: `--decision-reject` / `--ink-on-paper`
  - Promote to candidate: `--decision-promote` / `--ink-on-paper`, with a 1px inner border in the same color darkened 20% — the inner border signals "this is the formal action"; the button is visually distinct (wider, inner-bordered) so it is never mis-clicked.
- Disabled state (Reject without reason, Promote without evidence): 40% alpha, cursor `not-allowed`.
- Focus ring: 2px `--accent-phosphor`, 2px offset, for all four.

### 6.10 Status pill

```
  ┌──────────────┐
  │ ● DARK COMET │   ← kind pill (dark comet)
  └──────────────┘

  ┌──────────────────────────────┐
  │ CANDIDATE · 2026-05-18       │   ← post-promote pill
  └──────────────────────────────┘

  ┌──────────┐
  │ ok       │   ← pipeline-health pill
  └──────────┘
```

- Pill container: `--radius-pill`, padding `--sp-1` vertical × `--sp-3` horizontal, 11px uppercase mono, letter-spacing 0.08em.
- Kind pills: background is the kind hue at 18% alpha, text is the kind hue at 100%. A 6px filled dot in the same hue precedes the label.
- Candidate (post-promote) pill: background `--decision-promote` at 18% alpha, text `--decision-promote`, includes promotion date in mono.
- Health pills: background at 18% alpha of the health hue, text 100%.
- Entry animation: 120ms fade + 4px y-translate up from start. Never bouncy.

### 6.11 Empty-state card

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│                  ✧        ·    ·                         │
│                     ·  ·         ·                       │
│                   ·          ·                           │
│                                                          │
│           Nothing unusual tonight.                       │
│                                                          │
│   14,823 alerts ingested · 412 tracklets linked          │
│   last run mjd 60832.41 · thresholds-v1.yaml             │
│                                                          │
│       "What the survey does not find is also             │
│        a result." — after Wright et al. 2018             │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

- `.content-prose` width (680px), centered in main column, `--sp-8` margin top.
- Decorative constellation motif at top — a small inline SVG of 6–10 dots connected by thin strokes in `--accent-phosphor-dim`, different every page load (seeded by date so it's stable within a day).
- Verdict: Fraunces 500, 36px, `--text-primary`.
- Counts line: Inter Tight 16px, `--text-secondary`.
- Provenance line: mono 13px, `--text-tertiary`.
- Quote block: Inter Tight italic 15px, `--text-secondary`, max-width 52ch.

### 6.12 Pipeline-health sparkline

```
  INGEST LAG (24h)                               current: 3.2s   ok
  ────────────────────────────────────────────────────────────────
   ·     ·      ·                                    ·        ·
    ·   ·   ·      ·    · ·   ·   ·     ·    ·    ·     · ·
                                                                 ───── 5s line
```

- Label strip (mono 13px): metric name left, current value + health pill right.
- 1px `--divider` rule below the label strip.
- Sparkline SVG: 240×40, stroke 1.5px `--accent-phosphor`, threshold line in `--text-tertiary` dashed 1px with inline right-edge label.
- No filled area under the line (area fill reads as "dashboard stock art"; we want instrument-panel honest).

---

## 7. Motion

Streamlit-compatible means CSS transitions on inline-styled or class-swapped elements. No JS-driven animation libraries.

**Defaults:**
- Transition duration: 160ms for small state changes (hover, focus), 240ms for entry animations (pill fade-in, card appear).
- Easing: `cubic-bezier(0.2, 0.0, 0.0, 1.0)` — a calm ease-out with no overshoot. Defined as `--ease-calm`.

**Specific behaviors:**
- **Page transitions:** none. Streamlit re-renders the main column on nav click; we do not attempt to cross-fade. A crisp swap is more honest than a fake animation.
- **Card hover:** 160ms background transition from `--surface-card` to `--surface-card-hover` plus a 160ms border-left width transition from 0 → 2px in `--accent-phosphor`. No scale, no translate.
- **Status pill enter:** 240ms opacity 0 → 1 and translateY(4px) → 0, `--ease-calm`. Applied via a `.pill-enter` class toggled by Streamlit on re-render.
- **Decision action bar button press:** 80ms scale(1) → scale(0.98) on `:active`. No color change during active beyond what `:active` already provides.
- **Empty-state entry:** 320ms fade-in on the whole block, nothing else. No staggered children animation.
- **Focus outlines:** instant (0ms) — accessibility requires no delay.

**Explicit DO-NOT-DO list:**
- No carousels. Ever. Cutouts are shown as a strip, not a slider.
- No modals with scrim. Detail views are inline pages, not overlays (ADR-style decision: inline keeps browser-native back button meaningful).
- No bouncy easing (`cubic-bezier(0.68, -0.55, 0.27, 1.55)` and friends). This is a reference-grade tool. Bouncy motion reads as toy.
- No parallax on background. The noise texture stays put.
- No animated gradients or shimmer on loading states. Loading uses a static `_______` monospace placeholder with a subtle 1.4s opacity pulse between 0.5 and 0.8 — no shimmer-sheen SaaS skeleton.
- No typewriter text effect. No number count-up animation on the Tonight summary tiles — counts snap to final value.

---

## 8. Anti-patterns (project-specific)

Hard nos, not preferences. Violating these violates the UX brief.

1. **Red / green as the only status signal.** Color-vision safe requires shape + text, not just hue. Health status uses pills with text labels (`ok`, `warn`, `stale`, `err`) and the semantic colors are re-used across decision + health for consistency.
2. **"Alert!" language.** No exclamation marks, no "breaking", no "spotted", no "flag raised", no "anomaly detected tonight!" framing. The word "alert" refers to Rubin alert packets (pipeline input), never to watch-list entries (pipeline output). See UX brief §5.
3. **Stock space imagery.** No nebulae JPEGs, no Hubble Deep Field banners, no illustrated astronauts, no rocket emoji, no telescope hero images. The only imagery is real data: the 63×63 cutouts, the orbit SVG, the light curve. The decorative constellation motif on empty states is a tiny inline dot-graph, not a photograph.
4. **UAP / UFO spectacle framing.** PRD §1 is explicit: this is not a UAP detector. Never use "alien", "unidentified object" as a title, "could this be…", "mystery", or any breathless copy. The watch-list is dark comets and ISOs — both are mundane-but-scientifically-interesting Solar System bodies. Design for that emotional register.
5. **"Discovery" anywhere outside the explicit Promote action.** See UX brief §5.
6. **Tabs inside tabs.** One level of tabs max (dark comets / ISO on Watch List). Everything else is a single scrollable page.
7. **Auto-refresh loops.** This is a once-a-day review tool. No polling, no live stream view. Streamlit's manual rerun is fine.
8. **Skeuomorphic telescope / clipboard / space-cockpit chrome.** The aesthetic is observing journal, not 2010-iPad-nautical. No faux wood grain, no bolt rivets, no radar sweep on pipeline-health.
9. **Giant CTAs on the home page.** No "Get started" button. No onboarding modal. The user built and runs this themselves; if they can't find the nav rail, design has failed them.
10. **Dark-pattern re-engagement.** No "you haven't visited in N days" nudges. The tool respects the user's time.

---

## 9. Accessibility basics

- Minimum body font 14px; default 16px.
- All interactive elements have a visible focus ring (`--accent-phosphor`, 2px, 2px offset).
- Color contrast: `--text-primary` on `--bg-deep` is 12.4:1 (AAA); `--text-secondary` on `--bg-deep` is 7.8:1 (AAA); `--ink-on-paper` on `--surface-paper` is 12.1:1 (AAA).
- Kind + health status always carries text, not color alone (see §8.1).
- Prefers-reduced-motion: respected — all transitions shorten to 0ms when `@media (prefers-reduced-motion: reduce)` is active.
- Keyboard: nav rail is tab-navigable, action bar buttons are in natural order (Accept, Defer, Reject, Promote).

---

## 10. File map

- This file: `docs/ux/design-system.md` — the human-readable spec.
- Tokens + utilities in CSS: `dashboard/static/theme.css`.
- Component implementations: `dashboard/components/*.py` (built on top of the CSS utility classes and Streamlit primitives — out of scope for this document).
- Page layouts: `dashboard/pages/*.py` — one file per page in §3 of the UX brief.

*End of design system v0.1.*
