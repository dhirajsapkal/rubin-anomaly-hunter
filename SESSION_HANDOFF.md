# Session Handoff — 2026-04-22

**Status:** dashboard is live and functional; awaiting Playwright MCP to do a real visual QA pass.

This file is the fast-read orientation for a new Claude session picking up mid-work. Read `CLAUDE.md` → this file → then `docs/decisions/` entries as needed.

---

## Where we are

**The project exists.** PRD, 12 ADRs, pipeline scaffold, synthetic demo dataset, 5-page Streamlit dashboard. Everything is committed except this session's redesign work — see "Uncommitted at handoff" below.

**Design direction** was pivoted mid-session from "Observatory Night-Log" to **Mission-Control Modern** after user feedback. See ADR-0011.

**Information architecture** was pivoted from data-first to **narrative-first** after user said the original UI didn't explain *what's weird* about each entry. See ADR-0012. Added `dashboard/lib/narrative.py` — generates plain-language explanations + ranked hypotheses from existing entry data.

---

## What's running

- **Streamlit dashboard** on `http://localhost:8701/` — a background process from this session. If it's down, start with `streamlit run dashboard\app.py` or `scripts\run_dashboard.bat`.
- **Demo SQLite** at `data/demo.sqlite` with 4 open watch-list entries (3 dark comets + 1 ISO) + 7 archived decisions. Regenerate any time via `python scripts\make_demo_db.py`.
- **Note:** during testing, entry_id=1 was accidentally decided as "accept" via an AppTest harness misconfiguration. It appears in the Archive now instead of the Watch List. This is harmless — just regenerate the demo DB if you want a pristine 5-entry state.

---

## What the user just installed

- **`frontend-design` plugin** — Anthropic's visual design skill. Invoked it via `Skill` tool earlier this session; it guided the redesign direction. Already loaded into the session.
- **Playwright MCP** — the user just ran `claude mcp add playwright -- npx @playwright/mcp@latest`. After a Claude Code restart, browser tools (`browser_navigate`, `browser_take_screenshot`, `browser_snapshot`, `browser_console_messages`, `browser_click`, `browser_type`, etc.) will appear in the tool list.

---

## Next action for the new session

**Visual QA pass of the dashboard using Playwright.** Run through these in order:

1. `browser_navigate` to `http://localhost:8701/`
2. Take a screenshot of the Tonight page. Verify the hero numeric renders in amber, the telemetry bar at top, the "TONIGHT'S LEAD" strip picks the ISO entry (id=5), and the sparkline tile renders.
3. `browser_console_messages` — any CSS warnings, font 404s, or backdrop-filter failures? (The user reported a "random black square" earlier; we eliminated the suspected cause, but Playwright will confirm cleanly.)
4. `browser_click` into Watch List → confirm each row shows its "what's weird" secondary line:
   - Entry 4: *"non-grav signature — but a systematic is suspected"*
   - Entry 5: *"hyperbolic orbit matching a known iso"*
5. Click into entry 5 (the 3I/ATLAS-like ISO) → screenshot the Candidate Detail page. Verify:
   - Amber left-accent bar on the card-paper top
   - "WHAT'S WEIRD ABOUT THIS" headline: *"Hyperbolic orbit matching a known ISO"*
   - "WHAT IT COULD BE" cards with LEADING (Rediscovery of a known ISO) → PLAUSIBLE × 2 → UNLIKELY order
   - Hypothesis chevrons rotate on `<details>` expand
   - Orbit-fit grid has 9 rows with symbol/value/gloss columns
6. Click into entry 4 (suspicious systematic dark comet) → verify the leading hypothesis pill is SYSTEMATIC (red border) and the narrative text explains the chip correlation concern.
7. Resize viewport to 1280 px (minimum supported per PRD §N). Check that the 8-column watch-list grid doesn't collapse badly.
8. Hover a cutout thumbnail on Candidate Detail — the `scale(1.75)` transform should fire.
9. Report findings with concrete screenshots. Expect minor polish items; the IA and narrative generator have been tested via AppTest so the Python side is known-good.

---

## Uncommitted at handoff

The last committed revision (`d0948f5`) is the initial scaffold with the old Observatory Night-Log design. **All redesign work from this session is uncommitted**, including:

- Complete `dashboard/static/theme.css` rewrite (Mission-Control Modern)
- `dashboard/lib/theme.py` `_STREAMLIT_OVERRIDES` rewrite
- New `dashboard/lib/narrative.py`
- Hero numeric + telemetry bar + lead-story components in `dashboard/lib/components.py`
- Watch-list row restructure (adds `wle-row__main` + `wle-row__whatsweird`)
- Orbit fit block rewrite (3-column grid with plain-language glosses)
- Candidate Detail page IA rewrite (narrative-first)
- Tonight page hero + lead-story
- ADR-0011 + ADR-0012
- This handoff file

Commit message should be along the lines of:

```
Redesign: Mission-Control Modern visual direction + narrative-first IA

- Complete theme.css rewrite (IBM Plex, electric amber accent, ops-console
  feel, gradient mesh, no backdrop-filter)
- dashboard/lib/narrative.py: derives why-flagged + ranked hypotheses from
  entry data (no new DB columns)
- Candidate Detail IA: narrative -> evidence -> data
- Watch List rows show one-line "what's weird" summaries
- Tonight page adds TONIGHT'S LEAD strip and 120px tabular-mono hero
- Orbit fit block renders as a 3-col grid with plain-language glosses
- ADR-0011 (visual direction), ADR-0012 (narrative-first IA)
- Bug fixes: status value mismatch (accept vs accepted), double-fire guard
  on decision actions, relative href -> absolute href for cross-page nav
```

---

## Known minor issues (candidates for fixes after Playwright QA)

- `docs/ux/brief.md` + `docs/ux/design-system.md` still describe the old Observatory Night-Log aesthetic. ADR-0011 notes they are partially superseded; a future pass should rewrite the affected sections rather than leave them stale.
- `.decision-bar` uses `position: sticky` to the block-container, not to the card itself (QA review F2 from earlier — deferred as polish).
- Cutouts are procedural synthetic imagery labeled "demo" — no real FITS data until live Fink stream is connected.
- `find_orb` and `heliolinc3d` wrappers run in mock mode unless the binaries are installed (ADR-0007, ADR-0008).

---

## Useful pointers

- **PRD:** `PRD.md` (17 sections)
- **Project orientation:** `CLAUDE.md`
- **All design reasoning:** `docs/decisions/` (README.md is the index)
- **UX brief:** `docs/ux/brief.md` (persona, language rules, decision semantics — authoritative)
- **Demo data:** `data/demo.sqlite` (regen via `scripts\make_demo_db.py`)
- **Dashboard entry:** `dashboard/app.py` (Streamlit multipage)
- **Narrative logic:** `dashboard/lib/narrative.py`
- **Theme:** `dashboard/static/theme.css` + `dashboard/lib/theme.py` `_STREAMLIT_OVERRIDES`

*End of handoff.*
