# ADR-0017 — Cloud-hosted execution: GitHub Actions cron + Streamlit Community Cloud

**Status:** Accepted
**Date:** 2026-04-23
**Supersedes:** —
**Superseded by:** —
**Amends:** ADR-0016 (Fink Kafka primary ingest) — adds a second supported runtime
(GitHub Actions Ubuntu runner) alongside WSL2. Does not change the ingest
mode or invariants.

## Context

ADR-0016 made Fink Kafka the primary ingest, with WSL2 as the supported runtime
because `confluent-kafka` + `librdkafka` build cleanly on Ubuntu but not on
native Windows. The follow-up `scripts/wsl/bootstrap.sh` automates that path.

After WSL install hit a BIOS-virtualization blocker mid-session (2026-04-23,
see `SESSION_HANDOFF.md`), the user asked whether the pipeline could run
free 24×7 without WSL. The honest answer is yes: GitHub Actions provides
2,000 free Ubuntu-runner minutes/month on private repos (unlimited on public),
and Streamlit Community Cloud hosts public-repo Streamlit apps for free.

The ingest cadence is naturally batched (~few-times/day is sufficient for the
science target — Rubin nightly cadence + Fink topic latency is order minutes,
not seconds). A 4-hour cron is well inside the free tier and well above the
required latency floor.

Two runtimes solve different needs:

- **Cloud (GHA + Streamlit Cloud):** unattended 24×7, no local install, no
  BIOS, no per-machine setup. The dashboard URL is shareable.
- **Local (WSL2):** fast iteration, interactive debugging, instant access to
  `live.sqlite` for ad-hoc queries.

These are complementary, not competing. Cloud handles production; local
remains the dev environment.

## Decision

Add a **GitHub Actions cron workflow** (`.github/workflows/pipeline.yml`)
that runs the live pipeline on Ubuntu every 4 hours, and use **Streamlit
Community Cloud** to serve the dashboard from `main`. State (the SQLite
detection DB and Parquet archive) flows between the two via a dedicated
`data` git branch — the workflow commits `data/live.sqlite` and rotated
Parquet files to `data`, the dashboard rehydrates from the latest commit
on that branch on first request.

Specifically:

- **Workflow trigger:** `cron: "0 */4 * * *"` plus `workflow_dispatch` for
  manual runs. ~30-min budget per run is generous; find_orb cache hit makes
  steady-state runs much faster.
- **Workflow build:** Python 3.11, install package with `[ingest]` extra,
  install system Kafka (`librdkafka-dev`), build Bill Gray's stack
  (`lunar` → `jpl_eph` → `sat_code` → `find_orb`) under `~/src/` exactly
  as `scripts/wsl/bootstrap.sh` does. **Cache** `~/src/find_orb/fo` and
  the supporting binaries between runs by content-addressing the upstream
  commits (cache key includes `git ls-remote ... HEAD`). ADR-0008 invariant
  preserved — binaries are built per-run inside the runner, never committed
  to the repo.
- **Secrets:** `FINK_CLIENT_YAML` (entire YAML pasted into a GitHub Secret;
  workflow writes it to `~/.finkclient/credentials.yml` at job start, never
  echoed). Optional `LASAIR_TOKEN` for the fallback path. The workflow
  reads no other secrets.
- **State commit:** after a successful run, `data/live.sqlite` and any new
  Parquet under `data/archive/` are force-pushed to a `data` branch. The
  branch is rebuilt each run from `main` + just the data files (orphan-style
  history is rewritten — we don't keep historical SQLite snapshots, the
  archive Parquet is the durable record per ADR-0009). This keeps `main`
  clean of data and keeps the `data` branch small.
- **Dashboard rehydrate:** on dashboard startup, if `data/live.sqlite` is
  not present locally (Streamlit Cloud starts from a fresh checkout each
  deploy, but the running container persists across requests), the
  dashboard fetches the latest `data/live.sqlite` from the `data` branch
  via raw.githubusercontent.com and caches it under `data/`. Refresh
  cadence: pull on each Streamlit cold-start; subsequent requests use the
  cached file. A small "last updated" timestamp surfaces in the dashboard
  footer.

WSL2 (Branch B in the handoff) remains supported and documented; nothing
in this ADR removes it. The bootstrap script is unchanged.

## Consequences

**New capabilities**

- Pipeline runs unattended 24×7 inside the free tier (2,000 min/mo on
  private repos; effectively unlimited on public).
- Dashboard URL is shareable — the user can send it to collaborators.
- No local Python, WSL, or BIOS setup required to operate.
- Iteration loop becomes: edit → push → ~60s for GHA + Streamlit redeploy.

**New obligations**

- The repo must be on GitHub. Private is fine for free GHA; public is
  required for free Streamlit Cloud. The user has chosen private for now;
  if Streamlit Cloud needs public, that's a future trade-off.
- `FINK_CLIENT_YAML` lives in GitHub Secrets — the user is responsible for
  rotating it. It is never logged by the workflow (set `mask` on the secret
  is automatic for `secrets.*`; the workflow additionally avoids `cat`-ing
  the file at any step).
- The `data` branch is force-pushed each run. **Never check it out on
  `main`.** The workflow uses a separate worktree to avoid clobbering the
  user's working copy.
- Cold-start dashboard fetch adds 1–2s latency to the first request after
  a Streamlit Cloud cold boot; subsequent requests are local-disk fast.
- find_orb build inside GHA takes ~8–15 min on a cold cache; ~30 s on a warm
  cache (binary restore only). First workflow run will be slow.

**Invariants preserved**

- ADR-0005 (two-stage gate): unchanged. The cloud runner can only produce
  watch-list entries; promotion still requires manual operator action.
- ADR-0006 (threshold lock): unchanged. Workflow reads the locked YAML.
- ADR-0008 (find_orb personal-use only): preserved by building inside the
  runner per job; **the binary is never committed**, never published as an
  artifact, never uploaded outside the runner. The cache stores it inside
  GitHub's per-repo cache scope (private to the repo).
- ADR-0009 (raw payloads persist verbatim, broker flags snapshotted at
  ingest): preserved — Parquet files are still written exactly as in the
  WSL path, and committed to the `data` branch under `data/archive/`.
- ADR-0010 (alert-only — no RSP): unchanged.
- ADR-0011, 0014, 0015 (visual direction, IA, typography): unchanged.
- ADR-0013 (Lasair REST fallback): unchanged. Workflow defaults to Fink;
  user can switch to Lasair via repository variable `RUBIN_HUNTER_INGEST`
  if Fink credentials lapse.
- ADR-0016 (Fink Kafka primary): unchanged ingest mode; this ADR only
  changes *where* the consumer runs.

**New failure modes**

- GHA quota exhaustion (private repos): if the user goes well over 2,000
  min/mo, jobs queue. Mitigation: 4-hour cron at ~10 min/run = 1,800 min/mo,
  inside the budget. If find_orb cache misses persistently, jobs creep
  toward 30 min each — alert on this in a follow-up.
- Streamlit Cloud cold start: first request after idle takes ~10 s. This
  is acceptable for a research-grade dashboard.
- `data` branch force-push race: only one workflow runs at a time
  (`concurrency: pipeline`), so no race.

## Alternatives considered

- **Self-hosted GHA runner on a Raspberry Pi / spare box.** Removes the
  GHA quota cap and the 6-hour job cap, but reintroduces local-machine
  pain that Branch A is meant to eliminate. Reject for now; revisit if
  quota becomes a constraint.
- **Render / Railway / Fly.io** with a worker dyno. All would work, all
  cost money for the always-on portion. GHA cron + Streamlit Cloud is
  free; pick free.
- **Modal / Replicate** for the pipeline. Modal has a generous free tier
  and great Python ergonomics, but adds a third platform. Stay on
  GHA + Streamlit Cloud — fewer moving parts.
- **Commit `live.sqlite` to `main`.** Pollutes history with binary diffs,
  bloats clones. The orphan `data` branch keeps the cost local to a single
  ref.
- **Use GHA artifacts instead of a `data` branch.** Artifacts expire after
  90 days and can't be fetched anonymously by Streamlit Cloud. Branch is
  durable + publicly fetchable.
- **Run the dashboard *inside* GHA.** GHA isn't a long-lived web host;
  Streamlit Cloud is the right tool.

## References

- PRD §§4, 6, 13 (M0 ingest milestone)
- ADR-0008 (find_orb personal-use), ADR-0009 (own history layer),
  ADR-0013 (Lasair fallback), ADR-0016 (Fink primary)
- `SESSION_HANDOFF.md` (2026-04-23) — Branch A vs Branch B trade
- `.github/workflows/pipeline.yml` — implementation
- `dashboard/lib/db.py` — rehydrate-from-data-branch helper
- GitHub Actions billing: https://docs.github.com/en/billing/managing-billing-for-github-actions
- Streamlit Community Cloud: https://share.streamlit.io
