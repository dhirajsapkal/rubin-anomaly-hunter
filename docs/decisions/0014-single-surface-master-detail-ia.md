# ADR-0014 — Single-surface master-detail IA (Tonight · Ledger · Health)

**Status:** Accepted
**Date:** 2026-04-23
**Supersedes:** ADR-0012
**Superseded by:** —

## Context

ADR-0012 established narrative-first information architecture for per-entry
detail pages: narrative → reasoning → evidence → data → media → decision.
That ordering was right and remains. What was wrong was the surrounding
navigation shell.

After live data landed (50 real Rubin alerts per night, typically one
watch-list entry or zero), the 5-page sidebar nav — Tonight, Watch List,
Candidate Detail, Archive, Pipeline Health — failed on several axes:

- **Tonight and Watch List rendered the same payload** on most nights.
  One was a stripped-down hero over the other.
- **Candidate Detail was a page you could navigate to empty.** With no
  `?entry_id` present it rendered a tombstone. A sidebar nav entry that
  greets you with a 404-feeling state is a breadcrumb wearing a page's
  clothes.
- **Archive and Pipeline Health were rare destinations** inflating the
  perceived complexity of the product 5x.
- **Drill-down cost full page reloads.** Clicking into an entry lost
  telemetry context, list context, and forced Streamlit to rerun every
  page widget.

A four-agent UX audit (2026-04-23) converged on this diagnosis
independently: the nav was a taxonomy dump, not navigation. See the
agents' reports at `tmp/qa-realdata/` context — the IA strategist, visual
director, data-storytelling lead, and interaction designer all reached
the same conclusion from different starting points.

## Decision

Collapse the dashboard to a single surface — **Tonight** — with a narrow
**master-detail grid** inside it (260 px left gutter listing tonight's
watch-list entries, right canvas showing the active entry's detail
stack). Two secondary destinations survive as discrete pages:
**Ledger** (former Archive, renamed to reinforce the append-only /
git-tracked framing) and **Health** (former Pipeline Health). Navigation
is a **56 px horizontal top strip** with three pills — `TONIGHT · LEDGER ·
HEALTH` — and a right-aligned pair of provenance chips (`INGEST: LIVE ·
ORBITS: MOCK`). The Streamlit sidebar page-nav is retired entirely.

Candidate Detail ceases to exist as a page. Its content becomes the
**canvas** inside Tonight, URL-addressable as `/?e=<entry_id>` (legacy
`/Candidate_Detail?entry_id=N` stops resolving; this is a personal tool
with no external linkers). The ADR-0012 reading order is preserved *inside
the canvas* via collapsible `<details>` bands:

- default-open: **narrative · why-flagged · hypotheses · context-rails**
- default-closed: null-hypothesis tests · orbit fit table · cutouts · light
  curve + orbit plots

## Consequences

**New capabilities**
- Drill-down without losing list context. The gutter stays visible while
  the canvas updates.
- URL-addressable state. `/?e=5` deep-links to an entry; browser back
  works; session cache-free.
- Population strip-plots on the canvas. A flagged entry shows up as an
  amber triangle against the 48 other tracklets tonight — answers "compared
  to what" that the old stack did not.
- Provenance scoped correctly. The mock-mode banner (which read as a
  system alert, confusing users) is retired; scoped provenance chips sit
  on the values that are actually mock.

**New obligations**
- Decisions still follow the URL-driven protocol (`?e=N&action=accept`,
  `?e=N&pending=reject`). ADR-0005 invariants unchanged: the pipeline
  never writes `status='promoted'`; only the Promote action with attached
  evidence does.
- Keyboard shortcuts (J/K/A/D/R/P) are **proposed but not implemented**
  in this ADR. Follow-up session can add them via a small
  `components.v1.html` injection; not a blocker for this architecture.
- Page files layout:
  - `dashboard/app.py` — Tonight (single-surface master-detail)
  - `dashboard/pages/1_Ledger.py` — former Archive
  - `dashboard/pages/2_Health.py` — former Pipeline Health
  - retired: `1_Watch_List.py`, `2_Candidate_Detail.py`, `3_Archive.py`,
    `4_Pipeline_Health.py`

**Invariants preserved**
- ADR-0005 (two-stage gate + strict language discipline) — intact.
- ADR-0011 (Mission-Control Modern palette + near-black base + amber
  accent) — intact. ADR-0015 amends its *typography* clause separately.
- ADR-0012 *reading order* — intact, relocated from "page" to "canvas
  band".

## Alternatives considered

- **Keep the 5 pages, add keyboard nav.** Rejected — doesn't fix the
  "nav is a breadcrumb" diagnosis; just makes breadcrumbs faster.
- **Command palette over pages.** Rejected — introduces a discovery
  surface for a one-user tool with only 3 real destinations.
- **Full SPA / React rewrite.** Rejected — Streamlit is a deliberate
  constraint (ADR-0002 personal-tool scope). Master-detail inside
  Streamlit via `st.html` + URL state is sufficient.
- **Modal dialog drawer per row click.** Considered — the IA strategist
  agent recommended this. Rejected in favour of gutter master-detail
  because the master-detail enables side-by-side compare (Shift-click,
  proposed follow-up) that a modal cannot.

## References

- PRD §§5, 6, 10, 15
- ADR-0005 (two-stage gate)
- ADR-0011 (Mission-Control Modern visual direction)
- ADR-0012 (superseded)
- 2026-04-23 four-agent UX audit (IA · visual · data-storytelling ·
  interaction) whose consensus drove this ADR
