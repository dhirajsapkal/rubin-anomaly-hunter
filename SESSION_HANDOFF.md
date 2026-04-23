# Session Handoff — 2026-04-23 (cloud build session)

**Status:** Cloud-hosted execution path (Branch A from the previous handoff)
is implemented and ready for the operator to wire up GitHub + Streamlit Cloud.
WSL Branch B remains supported but is no longer the recommended path.

Next Claude session: read `CLAUDE.md` → this file → ADR-0017. The work in
this session is uncommitted on the local Mac clone (the user has not asked
to commit). Ask before committing/pushing.

---

## What this session shipped

1. **ADR-0017** — Cloud-hosted execution: GitHub Actions cron + Streamlit
   Community Cloud. Amends ADR-0016 by adding a second supported runtime
   (Ubuntu GHA runner) alongside WSL2. Preserves all existing invariants
   — find_orb still built per-job and never committed (ADR-0008), raw
   alert payloads still persist verbatim (ADR-0009), two-stage gate
   unchanged (ADR-0005). Index updated in `docs/decisions/README.md`.

2. **`.github/workflows/pipeline.yml`** — full GHA cron workflow.
   - `cron: "0 */4 * * *"` plus `workflow_dispatch` for manual runs.
   - Builds Bill Gray's stack (lunar → jpl_eph → sat_code → find_orb)
     inside the runner with `actions/cache@v4` keyed on
     `git ls-remote ... HEAD` of all four upstreams.
   - Materialises Fink credentials from the `FINK_CLIENT_YAML` secret to
     `~/.finkclient/credentials.yml` with 0600 perms; never echoed.
   - Restores the previous `data/` tree from the orphan `data` branch
     before the pipeline runs (so the SQLite isn't reset every cron tick).
   - Force-pushes the new `data/` tree back to `data` via a temp worktree
     + refspec push (avoids worktree-already-exists race on re-run).
   - `concurrency: live-pipeline` serialises runs.

3. **`requirements.txt`** + **`.streamlit/config.toml`** — Streamlit Cloud
   build inputs. Requirements file is intentionally lean (`streamlit`,
   `numpy`, `requests`) — the dashboard runtime doesn't need the heavy
   pipeline deps. Config file applies the Mission-Control Modern theme
   (ADR-0011 + ADR-0015).

4. **`dashboard/lib/rehydrate.py`** — fetches the latest `data/live.sqlite`
   from the orphan `data` branch via `raw.githubusercontent.com`, with
   `If-Modified-Since` cache validation and atomic tempfile-rename writes.
   No-op when `RUBIN_HUNTER_REHYDRATE_URL` is unset (local dev).

5. **`dashboard/lib/db.py`** — `resolve_db_path()` now triggers a
   `_rehydrate_once()` call (Streamlit-cached) before checking
   `LIVE_DB_PATH.exists()`. New public accessor `rehydrate_status()` is
   ready for the data-source chip to surface fetch provenance.

6. **`README.md`** — new "Running 24×7 in the cloud (free tier)" section
   walks the operator through the GitHub + Streamlit Cloud setup.

---

## What the operator does next

1. Push this branch to GitHub (`git push -u origin main` after first
   committing the uncommitted work).
2. Add repository secret `FINK_CLIENT_YAML` (paste full Fink YAML).
3. Settings → Actions → General → Workflow permissions → "Read and
   write permissions".
4. Actions tab → `live-pipeline` → Run workflow (manual seed run).
   First run takes ~10–15 min to build find_orb; subsequent runs ~3 min.
5. Deploy at share.streamlit.io: branch `main`, entry `dashboard/app.py`.
6. In the Streamlit Cloud app's Secrets, set:
   ```
   RUBIN_HUNTER_REHYDRATE_URL = "https://raw.githubusercontent.com/dhirajsapkal/rubin-anomaly-hunter/data/data/live.sqlite"
   ```

After step 4 succeeds, the `data` branch will exist with a `data/`
subtree. After step 6, the live dashboard will fetch from it.

---

## Open follow-ups (not blocking)

- **Surface rehydrate provenance in the dashboard.** `rehydrate_status()`
  is plumbed but not yet rendered in the data-source chip. The next
  session should add a small "fetched X min ago from data branch" line
  to the Health page footer or the existing data-source chip in
  `dashboard/lib/theme.py`.
- **Workflow alerting on persistent cache miss.** If find_orb builds
  every run (cache key churn), each run creeps toward 30 min and
  monthly minutes balloon. Add a step that warns when build time
  exceeds 5 min.
- **Lasair token rotation** still pending from the prior session
  (`e33bb5e1c0000c9bce7eb0ac24820790212e83bf`). Verify rotated when
  the user mentions Lasair next.
- **WSL Branch B** scripts and ADR-0016 remain accepted; nothing about
  this session removes them. They're an alternative dev runtime, not
  a competitor to cloud production.

---

## Files touched this session (uncommitted)

**New:**
- `docs/decisions/0017-cloud-hosted-execution.md`
- `.github/workflows/pipeline.yml`
- `.streamlit/config.toml`
- `requirements.txt`
- `dashboard/lib/rehydrate.py`

**Edited:**
- `docs/decisions/README.md` — added ADR-0017 row
- `dashboard/lib/db.py` — wired `_rehydrate_once()` into resolver
- `README.md` — added cloud-deployment section

---

## Memory additions this session

In `~/.claude/projects/-Users-dhirajsapkal-Documents-personal-Vibecoding-experiments-Veera-ruben/memory/`:

- `project_overview.md` — project summary so future sessions skip re-reading PRD/CLAUDE.md
- `project_working_directory.md` — Mac path is "Veera ruben" (lowercase r), prior Windows path obsolete
- `project_open_fork.md` — *needs update next session: cloud branch resolved*
- `reference_secrets.md` — Fink/Lasair handling + open token rotation

The `project_open_fork.md` memory should be marked resolved after the
operator confirms the cloud setup is live.

*End of handoff.*
