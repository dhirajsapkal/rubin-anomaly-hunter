# Rubin Anomaly Hunter — Dashboard UX Brief

**Version:** 0.1 (design, pre-implementation)
**Owner:** Dhiraj Sapkal
**Date:** 2026-04-22
**Companion specs:** `PRD.md` (esp. §1, §5, §11, §15), `docs/decisions/0005-two-stage-gate.md`
**Sibling file:** `docs/ux/design-system.md`

---

## 1. Persona snapshot

**Dhiraj — hobbyist astronomer, technical background.**

- Runs this pipeline on his own Windows 11 machine, overnight and unattended.
- Opens the dashboard **once a day**, typically late evening, on the same machine that produced the data. No mobile access. No sharing.
- Comfortable reading orbit elements (a, e, i, q), non-grav residuals (A1/A2/A3), σ values, HEALPix, MJD, filter bands. Does not need tooltips for these.
- **Not** a professional researcher. Does not write papers from this. Does not submit MPC reports from this. Follow-up astrometry, if any, is arranged externally by licensed observers (PRD §1).
- Motivation: "Did Rubin catch anything weird tonight?" Curiosity, not career. Expects most nights to be empty (PRD §15, §11) and that is the desired state.
- Hates review burden. If the daily review ritual takes more than ~10 minutes on quiet nights, the project dies (PRD §15 "Personal sustainability" + §14 risk "Review burden").

Design implication: this is a **night-log** tool, not a dashboard-as-product. It should feel like a leather-bound observing journal you open by lamplight, not a SaaS admin panel.

---

## 2. Jobs-to-be-done (ranked)

1. **"When I open this, what's new since last time?"**
   First screen must answer this in < 3 seconds. Load delta, not inventory.
2. **"Is this watch-list entry real or just a known asteroid / artifact / streak?"**
   Surface the null-hypothesis-test outcomes (PRD §10) before the pretty pictures. Morphology, MPC xmatch, streak-adjacency, R-score. If these fail, the rest does not matter.
3. **"Show me the interesting thing in enough detail that I can decide accept / defer / reject / promote."**
   Cutouts (science / template / difference), light curve, orbit plot, Marsden residuals with σ, cross-broker agreement. One card, no tabs that hide load-bearing data.
4. **"What's my pipeline doing? Is it healthy?"**
   Ingest lag, dropped-alert rate, broker status, last successful `heliolinc3d` run, last `find_orb` run, tracklet count over the rolling window. Secondary page. Should be boring on a healthy night.
5. **"Show me the history of what I've reviewed."**
   Append-only audit log view. Filter by decision, by watch-list kind, by date range. Not editable. (PRD §F10 — audit log is append-only, git-tracked.)

Jobs 1–3 are the daily ritual. Job 4 is weekly-ish. Job 5 is occasional and mostly for self-audit / writing up methodology.

---

## 3. Information architecture

Five pages. Flat. No nested tabs inside tabs. Streamlit left-rail nav.

### 3.1 Tonight (home)

**Purpose:** answer Job #1. Landing page.

**Primary content:**
- One-line verdict: *"2 new watch-list entries since your last visit"* or *"No promotions. 14,823 alerts ingested, 412 tracklets linked."* The empty case is a feature, not a fallback (PRD §15, §11 "No promotions").
- Delta summary tile: new watch-list rows (dark-comet + ISO, separated), anything recently promoted to candidate, anything that fell out of the watch-list window.
- Last-run timestamp + pipeline mode banner (*Commissioning window* vs. *Discovery window* per PRD §5 — this is load-bearing context, never hide it).

**Secondary content:**
- Mini sparkline of nightly tracklet counts (last 14 nights) — gives a visual heartbeat.
- Next expected run time (Windows Task Scheduler hint).
- Link to full pipeline health page.

**Explicitly not on Tonight:** a "feed" of every alert ingested. That is noise.

### 3.2 Watch List

**Purpose:** the triage queue for Jobs #2 and #3.

**Primary content:**
- One row per open watch-list entry. Columns: watch-list kind badge (dark-comet / ISO), internal ID, first-seen date, arc length (N detections over T nights), MPC-match status, R-score, decision state (untouched / deferred).
- Two tabs at top: **Dark comets** (default — primary per ADR-0004) and **ISOs**. Both use the same row layout. Never merged into one tab with a filter — the populations are scientifically distinct and the UI should say so.
- Sort by first-seen desc by default. Filter by decision state.

**Secondary content:**
- Count pill per tab ("Dark comets · 4 open").
- Bulk-defer action (explicit, two-click) for when none of them merit deeper review tonight.

**Language invariant (ADR-0005):** this page is titled **Watch List**. The rows are **watch-list entries**. The word **Candidate** does not appear on this page except inside the explicit *Promote to candidate* action label on the detail card. The word **Discovery** does not appear on this page at all.

### 3.3 Candidate Detail

**Purpose:** one watch-list entry, all load-bearing data, decision action bar. Job #3.

**Primary content (top to bottom):**
1. Header strip — watch-list kind pill (dark-comet | ISO), internal ID, MJD first-seen, arc length, pipeline threshold version tag (e.g. `thresholds-v1.yaml`).
2. Null-hypothesis test panel (PRD §10) — seven checks as a labeled list with pass / fail / warn state. This is above the orbit fit because a failed null test means the orbit fit is moot.
3. Orbit fit block — a, e, i, q, Ω, ω, T_peri; Marsden A1/A2/A3 with σ; ascii-monospace layout (see PRD §11 card).
4. Tracklet summary — N detections across T nights, which bands, total arc span.
5. Cutout strip — science, template, difference for each of up to N detections. Click to enlarge inline (no modal).
6. Light curve — per-band, with detection MJDs marked.
7. Orbit sketch — top-down ecliptic view, with the fit orbit + Solar System planets for scale.
8. Cross-broker context — Fink / Lasair / ALeRCE state, snapshot time vs. re-query time (PRD §10 test 7).
9. Notes field — free text, append-only (timestamped edits).
10. **Decision action bar** (sticky at bottom of the card): Accept · Defer · Reject · Promote to candidate.

**Secondary content:**
- Raw alert payload download (parquet path) for reproducibility.
- Provenance: ingest timestamp, pipeline commit SHA, config tag, `heliolinc3d` version, `find_orb` version.

**Language invariant:** title is **Watch-list entry**, not **Candidate**, regardless of what the user is about to do with it. The only appearance of "candidate" on this page is the button label *Promote to candidate*, and (after promotion) a small pill that reads *Candidate — promoted YYYY-MM-DD*. See §5.

### 3.4 Archive

**Purpose:** Job #5. Everything previously reviewed.

**Primary content:**
- Table of every decision ever made, newest first. Columns: date decided, watch-list kind, internal ID, decision (accept / defer / reject / promote), reviewer-note excerpt.
- Filter bar: date range, kind, decision. Free-text search across notes.

**Secondary content:**
- Click a row to open read-only view of the historical Candidate Detail page — the state as it was at decision time, with the original cutouts and fit. This is the provenance view (PRD §N5, §F10).
- "Reopen" action exists only for entries in *Defer* state. Accepted / rejected / promoted are frozen.

### 3.5 Pipeline Health

**Purpose:** Job #4.

**Primary content:**
- Ingest lag (Lasair, Fink) — current value + 24h sparkline.
- Dropped-alert rate (PRD §F1 — target < 0.1%).
- Last successful stage per night: ingest, pre-filter, DB commit, heliolinc3d link, find_orb fit, MPC xmatch, threshold eval. Each is a green / amber / red dot with timestamp.
- Broker cross-match version drift indicator (PRD §10 test 7).
- Null-field budget tracker (PRD §V4) — entries/night over last 30 nights vs. budget line.

**Secondary content:**
- Disk usage (raw alert archive — PRD §4 "~30 GB/year").
- Commissioning-window vs. discovery-window state and threshold tag.
- Link to the latest `reports/YYYY-MM-DD.md` daily summary file.

---

## 4. Empty states

Most nights will have no promotions (PRD §11, §15). The empty state is the **expected** state and must be designed to feel calm and correct, not broken.

### 4.1 Tonight — no new watch-list entries

Full-card empty state, centered in the main column. Contents:

- A small decorative glyph (constellation-line motif, hand-drawn feel — see design system).
- A one-sentence verdict in the display serif: *"Nothing unusual tonight."*
- Secondary line in body text: *"14,823 alerts ingested · 412 tracklets linked · 0 watch-list entries."* Numbers are concrete. They prove the pipeline ran.
- Tertiary line in mono, muted: the MJD of the last ingest and the pipeline version tag.
- A quote rotator at the bottom (one of ~20 hand-picked lines from the astronomy literature — e.g. Sheikh's Nine Axes, Wright et al. on negative results, Seligman on dark comets). Rotates on page load, never animated.

Explicitly **not** in the empty state:
- No exclamation marks. No "Yay!" No confetti. Silence is the point.
- No "Check back tomorrow" prompt — the pipeline runs on a schedule, the user knows.
- No illustration of a telescope pointing at stars. Stock space imagery is banned (see §7).

### 4.2 Watch List — empty tab

Inside the Dark-comet or ISO tab when nothing is open:
- Mono line: `watch-list empty — all entries accepted / rejected / promoted.`
- Below it, a small link: *"View archive →"* (takes them to §3.4 filtered to that kind).

### 4.3 Archive — never reviewed anything yet

- One sentence: *"No decisions logged yet. The first watch-list entry you review will appear here."*
- Mono secondary line: the audit-log file path on disk.

### 4.4 Pipeline Health — pipeline has never run

- Gentle, honest: *"No run history. Start the pipeline to populate this page."*
- Mono line with the Windows Task Scheduler job name and expected next-run time (if scheduled).

### 4.5 Candidate Detail — entry no longer exists (deep-link stale)

- *"That watch-list entry is no longer in the active queue."*
- Link: *"View in archive →"* if it was decided, else *"Return to watch list"*.

**Design philosophy for empty states:** the tool's job is to tell the truth about the sky tonight. "Nothing" is a true and valuable answer (PRD §15 cites Wright et al. 2018 on publishing negatives). The empty state should feel archival, like the blank entries in an observing journal on cloudy nights, not like a broken app.

---

## 5. Strict language rules

These encode ADR-0005 and PRD §5 invariants. The UI **must not** deviate.

| Term | Where it appears | Where it must NOT appear |
|------|------------------|--------------------------|
| **Watch list** / **watch-list entry** | Nav item, page titles, row labels, badges, empty-state copy, daily summary | — |
| **Candidate** | Only as: (a) the *Promote to candidate* action button label, (b) a *Candidate — promoted YYYY-MM-DD* pill on an entry **after** that action has been taken, (c) the Archive page for entries with that frozen decision | Any pre-promotion surface. The Watch List page. The Tonight page (except inside a historical "promoted N days ago" line). Reports referring to alert-only output. Tooltips. Button tooltips. |
| **Discovery** | Nowhere in the UI. The word is reserved for external formal communication about a fully-promoted, follow-up-confirmed candidate, and even then is discouraged per §1 of the PRD. | Everywhere in the UI. No "new discovery", no "discovered tonight", no "discovery feed". |
| **Dark comet** / **ISO** | Tab labels, kind badges, filters, chart legends | — |
| **Alert** | Technical surfaces only (pipeline health, provenance, raw-payload links). | As a synonym for "watch-list entry" in user-facing copy. Alerts are pipeline input; watch-list entries are output. |

**Tone rules:**
- No "alert!" exclamations. No red urgency color on watch-list arrivals (PRD §1: "not a UAP/UFO detector"; the project is deliberately un-spectacular).
- No verbs like "flagged", "detected", "spotted" in user-facing headlines. The pipeline *produced* a *watch-list entry*. It did not *discover* anything (ADR-0005).
- Numbers first, adjectives never. "4 watch-list entries" beats "several interesting candidates".

---

## 6. Key interactions — the four decisions

Every watch-list entry ends its life in exactly one of these four terminal (or deferrable) states. The decision action bar on Candidate Detail (§3.3) is the only place these fire. All four write append-only records to `decisions.sqlite` with full provenance (PRD §F10).

| Action | Meaning | State transition | Reversible? |
|--------|---------|------------------|-------------|
| **Accept** | "Yes, this is a real, interesting watch-list entry — but I am not promoting it. Keep it in the archive as reviewed-and-real." | Open → Accepted (archived) | No. Terminal. |
| **Defer** | "I can't tell tonight. Show it to me again in N nights when there's more arc, or when broker flags may have updated." | Open → Deferred (returns to queue in N nights) | Yes — can be reopened. |
| **Reject** | "Null-hypothesis test X failed, or this is a known object, or I'm confident it is artifact / streak / known." A reason must be selected from the §10 null-hypothesis checklist. | Open → Rejected (archived with reason) | No. Terminal. |
| **Promote to candidate** | "External follow-up astrometry has been attached and the original signature holds under the extended arc. This entry transitions to candidate status per ADR-0005 Stage B." Requires attaching follow-up evidence (file upload or reference) before the action fires. | Open → Candidate (archived as promoted) | No. Terminal. Logged with evidence link. |

**Interaction details:**
- The action bar is four buttons, visually weighted so *Defer* is the default-looking one (most common outcome) and *Promote to candidate* is distinct (rare, serious — but not styled like a submit button; styled as a deliberate archival action).
- *Reject* opens an inline reason picker (radio list of the seven §10 tests + "Other — note required"). No reason → button stays disabled.
- *Promote to candidate* opens an inline evidence attacher (MPC report reference, file path, URL). No evidence → button stays disabled. This enforces ADR-0005 Stage B.
- Every action immediately writes to the audit log before updating the UI; if the write fails, the UI state does not change.
- Once a non-deferred action is taken, the Candidate Detail page becomes read-only for that entry and is navigable only through the Archive page.

---

## 7. Non-goals

These are explicitly **not** in scope for the dashboard UX:

- **No social features.** No sharing, no comments from other users, no "follow this candidate", no public links. This is a single-user tool on a single machine.
- **No export to third-party services.** No Slack integration, no Discord webhooks, no Twitter/Mastodon post button, no "share to ALeRCE". If the user wants to communicate externally, they do so outside this tool (PRD §17).
- **No notifications beyond local desktop toast.** No email, no SMS, no push, no webhooks. At most: an optional Windows 11 toast notification when a new watch-list entry lands (PRD §11, §F8). Opt-in, off by default.
- **No real-time streaming view.** The pipeline runs on a schedule; the dashboard is a daily-review tool, not a live feed. No auto-refresh on Tonight or Watch List.
- **No mobile / tablet layout.** Desktop only, astronomy-sized monitor assumed. Minimum supported width 1280px.
- **No light mode.** Astronomy context (§8).
- **No gamification.** No streaks, no badges, no "you've reviewed 100 entries!" The only numeric feedback is the honest counts on Tonight.
- **No in-app editing of thresholds.** Threshold lock is a git-tagged YAML commitment (ADR-0006). The UI reads `thresholds-v*.yaml` but never writes it.
- **No suggestive ML ranking of "most interesting" at the top of the queue.** The IsolationForest score (PRD §6 stage 5) is displayed as data on the Candidate Detail page but does not re-order the Watch List. Ordering is by first-seen, deterministic, auditable.

---

## 8. Dark mode only

The dashboard is dark-mode-only. Rationale:

- Use context: late-evening review at the operator's machine, often in a dim room. Preserves dark adaptation.
- Domain convention: observatory control rooms, planetarium consoles, and amateur observing apps (SkySafari, Stellarium red-light mode) are dark by default.
- Scope: a second theme doubles visual-QA surface area on a single-user tool. Not worth it.
- Accent: one bright accent (phosphor green or ember orange — see design system) on a deep ink background reads cleanly in dim light and does not require red/green as the only status signal (see anti-patterns in design system).

A future "observatory red" night-vision variant could ship if the user actually observes with the same machine, but it is out of scope for v1.

---

## 9. Cross-references

- Visual language, tokens, components, motion: `docs/ux/design-system.md`.
- CSS implementation of the design system: `dashboard/static/theme.css`.
- Functional requirements this UX serves: PRD §F8, §F9, §F10, §11.
- Non-functional requirements affecting the UX: PRD §N1 (Windows 11), §N9 (no cloud).
- Scientific invariants the UX encodes: ADR-0005 (two-stage gate), ADR-0004 (dark comets primary), ADR-0006 (threshold lock), PRD §10 (null-hypothesis tests), PRD §15 (empty is success).

*End of UX brief v0.1.*
