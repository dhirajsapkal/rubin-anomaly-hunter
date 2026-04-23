# Session Handoff — 2026-04-23 (end of session)

**Status:** Paused mid-WSL-install. User is rebooting to enable BIOS
virtualization. A follow-up question suggests they may pivot to a
**cloud-hosted (GitHub Actions + Streamlit Cloud) architecture**
instead of local WSL.

Next Claude session: read `CLAUDE.md` → this file → recent ADRs
(0013–0016) → decide which of the two branches below to execute.

---

## Where we are

**This session ships:**

1. **Complete dashboard redesign** (agency-style 4-agent audit → 3-pill
   top nav + single-surface master-detail Tonight + Mollweide sky map +
   14-night cadence bar + population strip-plots on canvas). ADR-0014
   + ADR-0015 accepted; ADR-0012 superseded. Live at
   `http://localhost:8701/` when streamlit is running.
2. **Honesty gate** on the pipeline — degenerate tracklets (Lasair
   aggregate-only, all-same-coord detections) are no longer fitted
   with mock noise. They're marked `undetermined`. The chip reads
   `ORBITS: UNDETERMINED` (new amber variant) instead of the
   misleading `MOCK`.
3. **Fink Kafka ingest path** (ADR-0016, supersedes ADR-0013 for
   production). New module `src/rubin_hunter/ingest/fink_ingest.py`
   extracts `diaSource` + `prvDiaSources` per alert → per-detection
   rows. Pipeline accepts `ingest_mode="fink"`. CLI flag `--ingest
   {lasair,fink}`. Smoke-tested on a synthetic alert: 3 distinct
   `(ra, dec, mjd)` points extracted correctly.
4. **WSL2 bootstrap scripts** at `scripts/wsl/`:
   - `bootstrap.sh` — installs apt deps, builds Bill Gray's find_orb
     stack (lunar → jpl_eph → sat_code → find_orb), builds heliolinc3d
     best-effort, creates Python venv with fink-client.
   - `setup_fink_creds.sh` — copies Fink YAML to
     `~/.finkclient/credentials.yml`.
5. **ADRs:** 0014 (IA), 0015 (typography), 0016 (Fink Kafka ingest).
   ADR-0012 and 0013 marked superseded.

**Uncommitted:** everything this session. The user has NOT asked to
commit. Ask first.

---

## Blocker: WSL2 failed to install

The user ran `wsl --install` in admin PowerShell. WSL 2.6.3 installed,
but Ubuntu failed with:

```
WSL2 is not supported with your current machine configuration.
Please enable the "Virtual Machine Platform" optional component and
ensure virtualization is enabled in the BIOS.
Error code: Wsl/InstallDistro/Service/RegisterDistro/CreateVm/HCS/HCS_E_HYPERV_NOT_INSTALLED
```

The user ended the session to enter BIOS and enable Intel VT-x / AMD-V
(or the machine's equivalent SVM Mode). On resumption, expected flow:

1. `wsl --install --no-distribution` (admin PowerShell) → reboot
2. Verify Task Manager → Performance → CPU → Virtualization: Enabled
3. `wsl --install -d Ubuntu` → create Linux username/password

---

## User's follow-up question (unresolved)

At the end of the session the user asked:

> can this be hosted somewhere free where it can run 24x7 (or at least
> whenever new data comes out). And will that mean I can skip
> installing wsl?

I answered **yes** and sketched the architecture (GitHub Actions +
Streamlit Cloud). The user has NOT confirmed which path they want. So
the **next session's first question** is:

> **Did you decide to go cloud (GHA + Streamlit Cloud, skip WSL) or
> local (finish WSL install now that BIOS is fixed)?**

Both paths are ready for me.

---

## Branch A — cloud-hosted (preferred recommendation)

**Free 24x7 via GitHub Actions + Streamlit Community Cloud.** Removes
all local-machine pain. Architecture:

- GHA workflow (cron every 2–6 hours) on Ubuntu runner:
  - checkout repo
  - build find_orb from Bill Gray source (cache between runs; ADR-0008
    compliant — never committed)
  - optionally build heliolinc3d
  - install fink-client in a venv
  - read Fink YAML from GitHub Secrets
  - run `python scripts/run_live_pipeline.py --ingest fink`
  - commit updated `live.sqlite` + Parquet archive to a `data` branch
- Streamlit Cloud reads the dashboard from `main`, pulls `live.sqlite`
  from the `data` branch.

**What I still need to write next session:**

- `.github/workflows/pipeline.yml` (the cron GHA)
- `.streamlit/config.toml` (Streamlit Cloud entry point)
- A small script that rehydrates `live.sqlite` from the data branch on
  dashboard startup
- Update `dashboard/lib/db.py` to fall back to a fetched-from-branch
  location if local `live.sqlite` isn't present

**What the user does next session:**

- Push the repo to GitHub (private is fine; GHA is free on private)
- Add two GHA Secrets: `FINK_CLIENT_YAML` (paste Fink credentials),
  optionally `LASAIR_TOKEN`
- Enable GitHub Actions
- Sign up at share.streamlit.io, point it at their repo's `main`

First real-orbit fit: ~15 min after the first GHA run.

**This path skips WSL entirely.** No BIOS. No local binary builds. No
local `data/live.sqlite`.

---

## Branch B — local WSL (if BIOS fix succeeds and user prefers local)

Everything needed is already scripted:

```bash
wsl -e bash "/mnt/e/Claude experiments/Veera Rubin/scripts/wsl/bootstrap.sh"
wsl -e bash "/mnt/e/Claude experiments/Veera Rubin/scripts/wsl/setup_fink_creds.sh" \
  "/mnt/c/Users/Main/fink_client.yml"
wsl -e bash -c 'source ~/.rubin-hunter.env && \
  source $RUBIN_HUNTER_VENV/bin/activate && \
  cd "/mnt/e/Claude experiments/Veera Rubin" && \
  python scripts/run_live_pipeline.py --ingest fink \
    --fink-max-messages 100 --fink-timeout-s 60'
```

User also needs to complete Fink signup at
`https://fink-broker.readthedocs.io/en/latest/services/livestream/`
and save the YAML to `C:\Users\Main\fink_client.yml` (path is a
suggestion; `setup_fink_creds.sh` takes the actual path as an arg).

After success: chip flips to `INGEST: LIVE · ORBITS: REAL`, first
real watch-list entry appears on the dashboard.

---

## Security follow-ups the user should still address

1. **Rotate the Lasair token** `e33bb5e1c0000c9bce7eb0ac24820790212e83bf`
   — it appears in this chat transcript and in
   `.claude/settings.local.json` (which I have already added to
   `.gitignore`). The token is still valid as of session end.
2. **Fink YAML**, once the user has it, should go into GitHub Secrets
   (Branch A) or `~/.finkclient/credentials.yml` in WSL (Branch B),
   never into the repo.

---

## Files changed this session (uncommitted)

**New:**
- `dashboard/lib/skymap.py` (Mollweide all-sky)
- `dashboard/lib/cadence.py` (14-night cadence bar + summary phrase)
- `dashboard/lib/strip_plot.py` (population rails)
- `dashboard/pages/1_Ledger.py` (renamed from Archive)
- `dashboard/pages/2_Health.py` (renamed from Pipeline_Health)
- `src/rubin_hunter/ingest/fink_ingest.py` (Fink alert → detection rows)
- `scripts/wsl/bootstrap.sh`
- `scripts/wsl/setup_fink_creds.sh`
- `docs/decisions/0014-single-surface-master-detail-ia.md`
- `docs/decisions/0015-display-typography-plex-sans.md`
- `docs/decisions/0016-fink-kafka-primary-ingest.md`

**Rewritten:**
- `dashboard/app.py` (Tonight = master-detail canvas)
- `dashboard/static/theme.css` (quiet canvas edition — ADR-0015
  typography, 3-pill top nav, master-detail grid, provenance chips)
- `dashboard/lib/theme.py` (sidebar hidden, `top_nav()` helper,
  `provenance_chips_for()` with UNDETERMINED variant)
- `dashboard/lib/narrative.py` (+`generate_night_lede`, tension-naming
  rewrite of `generate_why_flagged`)
- `dashboard/lib/db.py` (+`nights_for_cadence`,
  `detections_for_skymap`, `tracklet_population_rails`, resolver now
  prefers live regardless of watch-list emptiness)
- `src/rubin_hunter/pipeline.py` (honesty gate + fink ingest branch)
- `src/rubin_hunter/ingest/fink_consumer.py` (creds resolution
  hardened)
- `src/rubin_hunter/ingest/lasair_rest.py` (real LSST column names)
- `scripts/run_live_pipeline.py` (`--ingest` flag)
- `.gitignore` (+`.claude/settings.local.json`)
- `docs/decisions/README.md` + `0012*.md`, `0013*.md` (superseded
  status)

**Retired:**
- `dashboard/pages/1_Watch_List.py`
- `dashboard/pages/2_Candidate_Detail.py`
- `dashboard/pages/3_Archive.py`
- `dashboard/pages/4_Pipeline_Health.py`

---

## Memory additions this session

- `feedback_ux_agency_pattern.md` — deploy parallel specialist
  subagents for UI/UX audits with `/frontend-design`; synthesize
  before implementing.

Both memory files are in
`C:\Users\Main\.claude\projects\E--Claude-experiments-Veera-Rubin\memory\`
and indexed in `MEMORY.md`.

*End of handoff.*
