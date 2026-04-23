# Rubin Anomaly Hunter

A personal-scale anomaly-detection pipeline over the **Vera C. Rubin Observatory** (LSST) public alert stream. Primary target: **dark comets** (Seligman et al. 2023). Secondary target: **interstellar objects**. Single-machine, Windows 11, Python.

> **Strict scope:** this is not a UAP/UFO detector. It is not a broker. It does not claim discovery credit. Its value is flagging watch-list entries for human review and (if warranted) external follow-up requests. See `docs/decisions/0001-scope-narrowing-uap-to-iso.md`.

## Status

Pre-implementation, early scaffolding. The pipeline's data and compute layers are stubbed with working mock modes, and a Streamlit review dashboard runs against a deterministically-generated synthetic SQLite so you can exercise the full UI before live alerts are connected.

Commissioning-window thresholds are **not locked** — they will be frozen at a dated threshold-lock (target 2026-07-01) per ADR-0006.

## Documentation

Read in this order:

1. **`PRD.md`** — product requirements (17 sections, full spec).
2. **`CLAUDE.md`** — orientation for future Claude sessions: invariants, source of truth, ADR-maintenance protocol.
3. **`docs/decisions/README.md`** — architecture decision records (10 ADRs covering every substantive choice, with reasoning).
4. **`docs/ux/brief.md`** + **`docs/ux/design-system.md`** — dashboard UX and visual language.

## Quickstart — run the dashboard

Requires Python 3.11+ and the packages listed under `[dashboard]` in `pyproject.toml`.

```bash
# From the project root
pip install -e ".[dashboard]"
python scripts/make_demo_db.py        # seeds data/demo.sqlite with synthetic fixtures
streamlit run dashboard/app.py
```

On Windows you can also run:

```bat
scripts\run_dashboard.bat
```

(This regenerates `data/demo.sqlite` if missing, then launches Streamlit.)

Then open the URL Streamlit prints (default `http://localhost:8501`).

### What you'll see

The demo dataset contains:

- **4 open dark-comet watch-list entries** (one deliberately on the threshold boundary — a good "defer" candidate)
- **1 open ISO watch-list entry** with orbital elements matching **3I/ATLAS** (demo teaching case; the MPC cross-match note names it explicitly)
- **6 archived entries** (accepted / rejected / promoted) so the Archive page is populated
- **14 nights of pipeline-health metrics** so the Pipeline Health page is populated

### Five pages

| Page | Purpose |
|------|---------|
| **Tonight** (home) | What's new since your last visit. Empty state is a feature, not a fallback (PRD §15). |
| **Watch List** | Dark comets tab (primary per ADR-0004) + ISOs tab. Click a row to open detail. |
| **Watch-list entry** | Null-hypothesis tests, orbit fit (Marsden A1/A2/A3), cutouts, light curve, orbit plot, MPC cross-match, cross-broker context, decision action bar. |
| **Archive** | Append-only history of every decision ever made. Filterable. |
| **Pipeline Health** | Ingest lag, dropped-alert rate, linking + fit stats, stage status. |

## Strict language — why these terms matter

Per `docs/decisions/0005-two-stage-gate.md` (the two-stage gate):

- **Watch-list entry** — alert-only, pre-follow-up. The output of the pipeline.
- **Candidate** — a watch-list entry promoted only *after* external follow-up astrometry confirms the original signature. Rare. Serious.
- **Discovery** — reserved for external formal communication about a fully-promoted candidate. Banned in the UI.

The dashboard is deliberate about these terms. "Candidate" appears only as (a) the Promote button label, (b) the post-promote pill on archived entries. "Discovery" appears nowhere.

## Project layout

```
.
├── CLAUDE.md                           # orientation for future Claude sessions
├── PRD.md                              # product requirements
├── README.md                           # this file
├── pyproject.toml
├── configs/
│   └── thresholds-commissioning.yaml   # fluid until 2026-07-01 lock date
├── docs/
│   ├── decisions/                      # ADRs 0001-0010, README.md index, template.md
│   └── ux/                             # brief.md, design-system.md
├── src/rubin_hunter/                   # pipeline (data layer + compute layer)
│   ├── ingest/                         # Fink Kafka consumer + raw-alert persistence
│   ├── detection_db/                   # SQLite schema + HEALPix bucketing
│   ├── linking/                        # heliolinc3d subprocess wrapper (mock-capable)
│   ├── orbit/                          # find_orb subprocess wrapper (mock-capable)
│   ├── scoring/                        # dark-comet + ISO threshold evaluation
│   ├── gate/                           # two-stage gate + null-hypothesis tests
│   └── demo/                           # synthetic dataset generator
├── dashboard/
│   ├── app.py                          # Tonight page (Streamlit entry)
│   ├── pages/                          # Watch List, Candidate Detail, Archive, Health
│   ├── lib/                            # db, theme, components, mockimg
│   └── static/theme.css
├── data/                               # gitignored — demo.sqlite, raw alert archive
└── scripts/                            # make_demo_db.py, run_dashboard.bat/.sh
```

## External tools (install separately)

Both wrappers run in **mock mode** when the binaries are absent, which is fine for development and for exercising the dashboard. For scientifically valid output, install:

- **find_orb** (Bill Gray, Project Pluto) — https://www.projectpluto.com/find_orb.htm. Source-available, **not OSI-open** — personal use only, never redistribute. See ADR-0008.
- **heliolinc3d** — https://github.com/lsst-dm/heliolinc2. C++ build; WSL2 is an acceptable Windows fallback. See ADR-0007.

## Running 24×7 in the cloud (free tier)

Per **ADR-0017**, the project supports two runtimes. Local WSL2 is documented at `scripts/wsl/bootstrap.sh`. The cloud path runs unattended on GitHub Actions + Streamlit Community Cloud — no local Python or BIOS setup needed.

### One-time operator setup

1. **Push the repo to GitHub** (private is fine for GHA; public is needed for the free Streamlit Cloud tier).
2. **Add the Fink credentials secret.** Settings → Secrets and variables → Actions → New repository secret:
   - Name: `FINK_CLIENT_YAML`
   - Value: paste the entire contents of your `fink-client` `credentials.yml`. To get credentials: submit the Fink subscription form at https://forms.gle/2td4jysT4e9pkf889 (they email back a `username` + `group_id`), then follow https://doc.lsst.fink-broker.org/services/livestream/ to run `fink_client_register` which writes the YAML to `~/.finkclient/credentials.yml`. See https://github.com/astrolabsoftware/fink-client for the CLI.
3. **Allow workflow writes.** Settings → Actions → General → Workflow permissions → "Read and write permissions". The cron workflow uses the built-in `GITHUB_TOKEN` to push the orphan `data` branch.
4. **Enable Actions.** Actions tab → "I understand my workflows" if first-time. Run `live-pipeline` once via "Run workflow" to seed the `data` branch (first run takes ~10–15 min building Bill Gray's stack; subsequent runs hit the cache and finish in ~3 min).
5. **Deploy the dashboard** at https://share.streamlit.io → New app:
   - Repository: your fork
   - Branch: `main`
   - Main file path: `dashboard/app.py`
6. **Tell the dashboard where to fetch state.** In the Streamlit Cloud app's settings → Advanced → Secrets, add:
   ```
   RUBIN_HUNTER_REHYDRATE_URL = "https://raw.githubusercontent.com/<your-user>/<your-repo>/data/data/live.sqlite"
   ```
   (For private repos, use a personal access token with `repo` scope embedded in the URL — see Streamlit Cloud's docs on private-repo data access.)

### How it works

- `.github/workflows/pipeline.yml` runs every 4 hours. It builds find_orb from upstream source (cached between runs), pulls Fink alerts, runs linking + orbit-fit + scoring, and force-pushes the resulting `data/live.sqlite` + `data/archive/` to the orphan `data` branch.
- The Streamlit Cloud dashboard fetches `data/live.sqlite` from the `data` branch on first request (`dashboard/lib/rehydrate.py`) and caches it in-container.
- find_orb binaries are built per-run inside the GHA runner and never leave it. ADR-0008 invariant preserved.

For a one-off pipeline run from the Actions tab, use the **Run workflow** button — accepts `since_days` and `max_messages` overrides.

## Contributing

This is a personal project (ADR-0002). Issues and PRs are not expected. If you're a future Claude Code session working on it: read `CLAUDE.md` first, follow the ADR-maintenance protocol, and don't bundle `find_orb` anything.

## License

All original source in this repository is proprietary — personal use only. `find_orb` binaries, source, and derived ephemerides are **not** part of this repository and must not be committed; their license terms are governed by Project Pluto.
