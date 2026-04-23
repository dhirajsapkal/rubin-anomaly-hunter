# Product Requirements Document — Rubin Anomaly Hunter

**Version:** 0.1 (draft, pre-commissioning)
**Owner:** Dhiraj Sapkal (personal project)
**Date:** 2026-04-22
**Status:** Design — threshold-lock target 2026-07-01

---

## 1. Context & Motivation

The Vera C. Rubin Observatory (LSST) began public alert production on 24 February 2026. Alerts flow to nine community brokers (Fink, Lasair, ALeRCE, ANTARES, AMPEL, Babamul, Pitt-Google, SNAPS, POI) with **no data-rights gatekeeping** — anyone with an email can consume them. Current volume is ~800k alerts/night during early operations; full LSST cadence (~10M/night) is expected to ramp through late 2026.

This project is a **personal-scale, single-machine pipeline** that consumes Rubin's public alert stream to search for two classes of anomalous Solar System objects:

- **Primary target — Dark comets** (Seligman et al. 2023): low-activity or inactive asteroidal bodies exhibiting non-gravitational acceleration without visible coma, discovered as a distinct class in recent years. Rubin is expected to find many.
- **Secondary target — Interstellar Objects (ISOs)** (e.g., 1I/'Oumuamua, 2I/Borisov, 3I/ATLAS): objects on hyperbolic trajectories, expected Rubin yield 1–10/year (Hoover et al. 2022, Marceta & Seligman 2023).

Dark comets are the load-bearing target because **their anomaly signature (non-grav residuals without visible activity) is resolvable from short-arc, alert-only data**, whereas closing an ISO claim (eccentricity e > 1 with small σ) requires follow-up astrometry that this pipeline does not perform. Both targets share ≥90% of the pipeline; dark comets deliver a continuously useful output while ISOs appear as serendipitous discoveries.

### Honest scope statement
This is **not** a UAP/UFO detector (Rubin is the wrong instrument — focus at infinity, slewing, wrong FOV for atmospheric phenomena). It is **not** a broker, a classifier of known transients, or a replacement for MPC. It does **not** claim discovery credit: any watch-list object requires independent follow-up astrometry submitted by a licensed observer before a discovery claim is defensible; MPC credit for any such discovery flows to Rubin and the follow-up observatory, not this pipeline. The pipeline's value is **flagging candidates in real time for human review and (if warranted) external follow-up requests**, not closing the scientific case solo.

---

## 2. Goals and Non-Goals

### Goals
1. Ingest Rubin's public alert stream in real time and persist raw alert payloads for reproducible offline re-analysis.
2. Build a local multi-night detection database capable of linking Solar System object tracklets across nights.
3. Fit short-arc orbits (including Marsden-style non-gravitational terms A1, A2, A3) to each linked tracklet.
4. Flag two classes for human review:
   - Dark-comet watch-list: non-grav acceleration inconsistent with standard cometary outgassing, no visible activity in difference-image cutouts.
   - ISO watch-list: hyperbolic best-fit orbit with σ(e) small enough to warrant follow-up.
5. Retrospectively validate the pipeline against known objects — 3I/ATLAS in Rubin commissioning data, and 1I/'Oumuamua / 2I/Borisov in ZTF archive.
6. Maintain pre-registered, dated threshold locks that preserve scientific defensibility.

### Non-goals
- Full-sky classification of all transients.
- Competing with official MPC/Minor Planet Center data products.
- Operating as a service for other users.
- Any pixel-level analysis beyond the 63×63 cutouts bundled with alerts (pixel-level Rubin data is RSP-gated and not accessible to non-rights-holders).
- Real-time follow-up scheduling (human-in-the-loop only).
- Long-period variable stars, supernovae, kilonovae, or other transient science. Those are well-served by existing broker science modules.

---

## 3. Scientific Grounding

### Dark comets (primary)
A population of Solar System bodies showing non-gravitational acceleration in their orbital solutions while appearing inactive in imaging — no dust coma, no visible tail, no detectable gas emission. First formally described as a distinct class in Seligman et al. 2023 (ApJ 162:229), with ~7 objects known at that time; the population is expected to grow with Rubin-scale surveys. Physical explanations under investigation include small-body outgassing below imaging detection thresholds, radiation-pressure effects on low-density rubble, and H2/CO ice sublimation. The anomaly is **quantitative** (A1, A2, A3 residuals from orbital fit) rather than morphological, which makes them detectable from alert-only astrometry.

### Interstellar objects (secondary)
Bodies on unbound trajectories through the Solar System (e > 1). Confirmed cases:
- **1I/'Oumuamua** (2017) — famously showed non-gravitational acceleration without visible outgassing (Micheli et al. 2018, Nature 559:223); leading natural explanation is H2 outgassing (Bergner & Seligman 2023).
- **2I/Borisov** (2019) — unambiguously cometary.
- **3I/ATLAS / C/2025 N1 (ATLAS)** (2025) — confirmed ISO; MPEC 2025-N12 (2 July 2025), 319 observations by 4 July 2025. Rubin commissioning observations published (arXiv 2507.13409, v3 revised 7 April 2026).

**Closing an e > 1 claim is hard from short arcs.** Micheli et al. needed 818 observations over 80 days across multiple observatories for 'Oumuamua. On a typical Rubin 3-night tracklet with 4–8 detections, expect σ(e) ≈ 0.3; "unbound" vs. "high-e Centaur / Oort returner" does not resolve from alert-only data. This is why candidacy is gated in two stages (§5).

### References
- Seligman et al. 2023, ApJ 162:229 (dark comets as a class)
- Micheli et al. 2018, Nature 559:223 ('Oumuamua non-grav)
- Hoover et al. 2022, PSJ 3:71 (Rubin ISO yield)
- Marceta & Seligman 2023, PSJ 4:238 (ISO detectability)
- Sheikh 2020, IJA 19:237 (Nine Axes of Merit for technosignature-adjacent claims)
- Bergner & Seligman 2023, Nature 615:610 ('Oumuamua H2 outgassing)
- Jewitt & Seligman 2023, ARA&A (ISO review)

---

## 4. Data Sources

### Primary — Rubin alert stream (live)
- **Lasair-LSST** (https://lasair.lsst.ac.uk) — custom server-side SQL filter for fast-movers / unknown-SSObject candidates. Free signup, API token issued per user. Lasair-LSST explicitly preserves `SSSource`, `SSObject`, and `mpc_orbit` records (per https://community.lsst.org/t/expected-lasair-ssobjectid-behaviour/11534). Primary live tap.
- **Fink-LSST** (https://lsst.fink-portal.org) — subscribe to `fink_uniform_sample_lsst` as a redundant raw sample until Fink publishes a dedicated LSST SSO/tracklet topic. The `b_is_solar_system` block exists in Fink's Rubin filter code (`fink_filters/rubin/blocks.py`) but is not yet wired to a public topic; monitor Fink's release notes and swap to the SSO topic when it ships. Secondary live tap.
- **Schema:** `lsst.alert_packet` AVRO, spec at https://github.com/lsst/alert_packet and https://sdm-schemas.lsst.io/apdb.html.

**Expected early-ops caveat:** SSO alerts in April 2026 frequently arrive with `diaObject = null` and sparse/empty `prv_diaSources` (Fink's own code comments confirm this for SSOs). The pipeline does **not** rely on broker-side history; see §6 for local history accumulation.

### Calibration / replay rail — ZTF (archive + live)
- **ANTARES archive replay** (https://antares.noirlab.edu) — ZTF's 7-year alert archive for retrospective injection of 1I/'Oumuamua (2017) and 2I/Borisov (2019) astrometry. Mature replay tooling that Rubin does not yet offer.
- **Fink `fink_sso_fink_candidates_ztf`** — live ZTF SSO candidates for tracklet-linking code calibration while Rubin's SSO topic is absent. Not a science rail — calibration only.

### Retrospective validation datasets
- **MPC observations for 1I, 2I, 3I/ATLAS** via MPC Explorer (https://www.minorplanetcenter.net/db_search) and MPEC archive (https://minorplanetcenter.net/iau/lists/MPEC.html). ADES format; all three objects are public with no embargo.
- **Rubin commissioning data on 3I/ATLAS** — published in arXiv 2507.13409; astrometry tables in the paper's supplementary materials.

### Rate and volume budget
- Early-ops Rubin: ~800k alerts/night total → ~100–1,000 SSO candidates/night after `b_is_solar_system` filter. Trivially single-machine.
- Full LSST cadence (late 2026+): ~10M alerts/night; SSO candidates scale to ~10k/night. Still single-machine with HEALPix bucketing (§6).
- Raw payload persistence: ~80 KB/alert × 1,000 SSO/night = ~80 MB/night = ~30 GB/year. Local SSD fine.

---

## 5. Candidate Criteria (Two-Stage Gate, Pre-Registered with Commissioning Window)

This section defines the criteria for the two watch-lists. **Thresholds are not locked at v1.** Per the split-sample design adopted after peer review, numeric thresholds enter force at the **threshold-lock date** and not before.

### Commissioning window
- **Duration:** from first live ingest through **2026-07-01** (target; adjust if plumbing delays push it later).
- **Behavior:** all stages of the pipeline run end-to-end. Thresholds are fluid. Distributions of e, σ(e), non-grav residuals, and SSO-candidate counts are characterized against observed Rubin data and ZTF archive. Nothing from this window counts as a discovery claim.
- **Exit criterion:** peer-documented thresholds based on (a) observed noise distribution, (b) injection-test recall targets, (c) null-field false-positive budget. Locked in a git-tagged config file at `configs/thresholds-v1.yaml`.

### Discovery window
- **Start:** the commit that tags `thresholds-v1.yaml` as immutable.
- **Behavior:** pipeline evaluates alerts against frozen thresholds. Any subsequent threshold change starts a new tag (`thresholds-v2.yaml`) and a new discovery window; pre-v2 objects are grandfathered under v1 rules.

### Two-stage gate

#### Stage A — Watch-list (alert-only, real-time)
An object enters a watch-list when ALL of the following hold against frozen thresholds:

**Common gate (both watch-lists):**
- `≥ N_arc` detections linked into a tracklet spanning ≥ `T_arc` nights (placeholder — N_arc likely 5, T_arc likely 3; lock in commissioning)
- No MPC match within tolerance (known-object cross-match via MPC Explorer or `sbpy.data.Names`)
- No streak flag or streak-endpoint adjacency
- Reliability / real-bogus score above `R_min`

**Dark-comet watch-list (primary):**
- Best-fit Marsden A1, A2, or A3 non-grav term above `A_min`
- σ(A_k) / |A_k| < some threshold (measurement, not noise)
- Zero visible coma / tail in difference-image cutouts (morphology features within stellar-PSF tolerance)
- Orbit bound (e < 1 − σ)

**ISO watch-list (secondary):**
- Best-fit e > 1
- σ(e) < `sigma_e_max`
- Best-fit perihelion q within Solar-System-plausible range

Watch-list entries are stored, cutouts archived, cross-broker context recorded, and the operator is notified once per day (not per event).

#### Stage B — Candidate (after external follow-up)
Watch-list → candidate promotion requires:
- Independent astrometry from outside the Rubin alert stream (amateur network observation, additional Rubin passes over subsequent nights, MPC-listed follow-up)
- Refit with extended arc shows the original signature holds
- Null-hypothesis tests in §10 all resolved

Only candidates (not watch-list) may be discussed as potentially novel in any external communication.

---

## 6. System Architecture

Single-machine Python pipeline, five stages plus persistence layer.

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Lasair-LSST     │     │  Fink-LSST       │     │  ANTARES (ZTF    │
│  SQL filter      │     │  uniform_sample  │     │  archive)        │
└────────┬─────────┘     └────────┬─────────┘     └────────┬─────────┘
         │                        │                        │
         │  Kafka / REST          │  Kafka                 │  REST
         ▼                        ▼                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 1 — INGEST                                                   │
│  Persist raw AVRO payload to local store (Parquet + Git-LFS or      │
│  object store). No mutation. Broker cross-match flags snapshotted   │
│  at ingest time (they change later).                                │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 2 — PRE-FILTER                                               │
│  Fast-mover selection via broker-side filters where possible        │
│  (Fink b_is_solar_system, Lasair custom SQL). Client-side fallback: │
│  motion > threshold, no coma-like morphology flags.                 │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 3 — DETECTION DATABASE                                       │
│  SQLite with HEALPix nside=2^14 spatial bucket index. Every         │
│  detection keyed by (diaSourceId, ra, dec, MJD, band, flux, flags). │
│  Cutouts stored on disk; DB holds path + hash. Broker-provided      │
│  context fields persisted alongside but never trusted as            │
│  authoritative (they are re-queryable and versioned).               │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 4 — NIGHTLY TRACKLET LINKING                                 │
│  heliolinc3d subprocess over the rolling detection window (e.g.,    │
│  last 14 nights). Outputs linked tracklets + quality flags. Do NOT  │
│  reimplement Kubica-style linking in Python.                        │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 5 — ORBIT FIT & SCORING                                      │
│  For each tracklet:                                                 │
│    1. Export to ADES via sbpy                                       │
│    2. find_orb batch subprocess ('fo') with Marsden A1/A2/A3        │
│    3. Parse JSON orbital elements + covariance                      │
│    4. MPC known-object cross-match                                  │
│    5. Evaluate against frozen thresholds → watch-list routing       │
│    6. coniferest IsolationForest on feature vector for active-      │
│       learning feedback over time                                   │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  REVIEW UI                                                          │
│  Streamlit dashboard OR Jupyter notebook. Daily summary +           │
│  per-watch-list-entry card (cutouts, light curve, orbit, MPC        │
│  xmatch, cross-broker status, accept/defer/reject). All decisions   │
│  written to audit log.                                              │
└─────────────────────────────────────────────────────────────────────┘
```

### Design notes
- **Raw alert payloads are immutable at ingest.** Broker cross-match flags change over time; snapshot them at ingest and never re-query in place.
- **Tracklet linking is delegated.** `heliolinc3d` is the standard; implementing tree-based linking solo is not in scope.
- **Orbit fitting is delegated.** `find_orb` via subprocess with ADES input, JSON element output. No attempt to reimplement Marsden fitting in Python.
- **Spatial indexing.** HEALPix bucketing (via `healpy`) gives O(log N) cone searches on SQLite without SpatiaLite. Alternative: SpatiaLite if HEALPix buckets prove clumsy.
- **Active learning.** `coniferest.pineforest` (SNAD) provides an isolation-forest with human-in-the-loop labeling. Runs over the feature vector (orbital elements, residuals, morphology) not raw light curves.

---

## 7. Functional Requirements

| # | Requirement | Acceptance test |
|---|-------------|-----------------|
| F1 | Ingest Rubin alerts from Lasair-LSST SQL filter in real time | 24-hour continuous run; dropped-alert rate < 0.1% |
| F2 | Ingest Fink-LSST `fink_uniform_sample_lsst` as redundant tap | Parallel 24-hour run; cross-broker overlap ≥ 80% on SSO candidates |
| F3 | Persist raw AVRO payload verbatim with ingest-time broker flags | Replay any stored alert reproduces identical features |
| F4 | HEALPix-bucketed SQLite detection DB supports cone-search queries | Benchmark: 30-arcmin cone over 10M-row DB < 100 ms |
| F5 | Nightly tracklet linking via `heliolinc3d` | Recovery of ≥ 80% of known MPC objects in a test window |
| F6 | Per-tracklet orbit fit via `find_orb` with Marsden terms | On 3I/ATLAS commissioning arc, recover e > 1 to within paper's reported σ |
| F7 | Two-stage gate routing (watch-list A, watch-list B, candidate) | Every stage has a persisted audit record |
| F8 | Daily summary report (watch-list promotions, pipeline health) | Report delivered to local file + optional desktop notification |
| F9 | Review dashboard for watch-list entries | Each entry shows cutouts, orbit, MPC xmatch, cross-broker context |
| F10 | Decision audit log (accept / defer / reject) for every reviewed item | Audit log is append-only, git-tracked |
| F11 | Retrospective injection runner | Given MPC astrometry for any object, inject into ZTF archive and report recovery |
| F12 | Threshold-lock config is git-tagged and immutable once locked | Changing a locked threshold requires a new tagged version |

---

## 8. Non-Functional Requirements

| # | Requirement |
|---|-------------|
| N1 | Runs on Windows 11, Python 3.11+ |
| N2 | Single machine; no GPU required for v1 |
| N3 | All config in version-controlled YAML under `configs/` |
| N4 | Seeded randomness for every stochastic component (IsolationForest, MC sampling in orbit fits) |
| N5 | Full raw-alert + decision provenance — any published candidate can be regenerated from git commit + local archive |
| N6 | End-to-end processing of one night's alerts completes in < 2 hours |
| N7 | Unattended daily run via Windows Task Scheduler |
| N8 | Failure isolation: ingest failure does not corrupt the detection DB; linking failure does not affect prior nights |
| N9 | No shared infrastructure, no cloud dependencies for v1 |

---

## 9. Validation Plan

### V1 — Retrospective injection on ZTF archive (commissioning window)
Pull MPC astrometry for 1I/'Oumuamua and 2I/Borisov. Inject as synthetic alerts into a ZTF archive replay window around their real discovery dates. Run the pipeline end-to-end. **Success criterion:** both objects enter the ISO watch-list under commissioning-phase thresholds; recall ≥ 80% on injected copies across noise perturbations.

### V2 — Rubin commissioning rediscovery of 3I/ATLAS (commissioning window)
Replay Rubin's alert archive over the window covering 3I/ATLAS's Rubin observations (cf. arXiv 2507.13409). Run the pipeline. **Success criterion:** 3I/ATLAS enters the ISO watch-list; its tracklet links correctly; its non-grav fit is consistent with the published paper's values within stated uncertainties.

### V3 — Dark-comet rediscovery on archive (commissioning window)
For each of the published dark comets in Seligman et al. 2023 and subsequent additions, check whether any have ZTF or Rubin alert coverage. For those that do, replay and confirm watch-list entry.

### V4 — Null-field baseline (commissioning window)
Run the pipeline on a week of Rubin alerts with known absence of published dark-comet or ISO candidates. **Success criterion:** watch-list entry rate matches the pre-registered null-field budget (target defined at lock time — likely ≤ 5 entries/night for dark-comet watch-list, ≤ 1/week for ISO watch-list).

### V5 — Cross-broker consistency spot check (discovery window)
Once per week, pick a random watch-list entry and query the same source via ALeRCE and any other active broker. **Success criterion:** no single-broker pipeline bug produces candidates that disappear under independent broker lookup.

Recall and precision targets are pinned at the threshold-lock date in `configs/thresholds-v1.yaml` based on observed commissioning distributions.

---

## 10. Null-Hypothesis Tests

Every watch-list entry must be checked against the following mundane explanations. Failures → rejection unless explicitly flagged for review.

1. **Known Solar System object.** Full MPC cross-match including recent numbered asteroids, TNOs, and Centaurs. Tolerance per object class.
2. **Standard cometary outgassing.** If non-grav fit is consistent with typical comet A1, A2, A3 magnitudes *and* morphology shows any coma indication in cutouts → normal comet, rejected from dark-comet watch-list (but fine for ISO if hyperbolic).
3. **Image artifact or bad subtraction.** Reliability / real-bogus score below R_min; difference-image cutout shows ringing or negative companion.
4. **Satellite streak residual.** Streak flag OR streak-endpoint within some angular tolerance. (Critical — Starlink-era streaks are ~30–40% of twilight exposures per Tyson et al. 2020.)
5. **Short-arc ambiguity.** Arc shorter than N_arc or tracklet quality flag indicates linking uncertainty — requeue, not promote.
6. **Instrument systematic.** Entry correlates suspiciously with a specific CCD, filter, airmass bin, or moon phase in the daily distribution. Trigger investigation.
7. **Broker flag version drift.** Re-query broker context at review time; if flags have changed meaningfully since ingest, investigate before promoting.

---

## 11. Outputs and Review UX

### Daily summary (unattended)
Plain-text or Markdown report written to `reports/YYYY-MM-DD.md`. Structure:
- Alerts ingested (Rubin + ZTF-calibration), tracklets linked, orbits fit.
- Watch-list promotions (dark-comet, ISO) with one-line per entry.
- Pipeline-health section: ingest lag, dropped-alert rate, broker status.
- **If all lists empty: one-line "No promotions."** This is expected for most nights and is success, not failure.

### Review dashboard (Streamlit)
One card per watch-list entry:

```
┌────────────────────────────────────────────────────────────────┐
│ WATCH-LIST: DARK COMET    alertId: 0x1a2b3c4d  2026-05-12     │
├────────────────────────────────────────────────────────────────┤
│ Orbit (find_orb):                                              │
│   a = 3.24 ± 0.12 AU    e = 0.41 ± 0.03    i = 8.2° ± 0.4°   │
│   A1 = 1.4e-8 ± 2e-9 AU/d²  A2 = 3e-10 ± 1e-10              │
│ Tracklet: 7 detections over 4 nights                          │
│ MPC match: none within 30'                                    │
│ Morphology: PSF-consistent in all 7 cutouts (no coma)         │
├────────────────────────────────────────────────────────────────┤
│ [science]  [template]  [difference]  [light curve]  [orbit]   │
├────────────────────────────────────────────────────────────────┤
│ Cross-broker: Fink (agrees), ALeRCE (not observed)            │
│ Notes: _____________________________________________           │
│                                                                │
│  [ACCEPT]  [DEFER]  [REJECT]  [PROMOTE TO CANDIDATE]          │
└────────────────────────────────────────────────────────────────┘
```

Every decision persists to `decisions.sqlite` with full provenance.

### Auto-triage
Default: review dashboard only opened on demand. Desktop notification fires only when a new entry is promoted to watch-list. No notification on routine alert ingest.

---

## 12. Tech Stack

| Component | Library | Notes |
|-----------|---------|-------|
| Alert ingest (Kafka) | `fink-client ≥ 10.0` | https://github.com/astrolabsoftware/fink-client — `fink_consumer -survey lsst` |
| Alert ingest (REST / custom SQL) | `lasair` (PyPI) | https://github.com/lsst-uk/lasair-client |
| ZTF archive replay | `antares_client` | https://noao.gitlab.io/antares/client/ |
| AVRO schema decoding | `fastavro` | https://github.com/fastavro/fastavro |
| Astronomy core | `astropy` | coordinates, FITS stamps, time |
| SSO plumbing / ADES I/O | `sbpy` | https://sbpy.readthedocs.io |
| Tracklet linking | `heliolinc3d` | https://github.com/lsst-dm/heliolinc2 (subprocess; do NOT reimplement) |
| Orbit fitting | `find_orb` (Bill Gray) | https://www.projectpluto.com/find_orb.htm (subprocess; `fo` batch mode with Marsden A1/A2/A3). Source-available, **not OSI-open** — personal use only, no redistribution without Gray's permission. |
| Spatial indexing | `healpy` | HEALPix bucketing in SQLite |
| Anomaly scoring | `coniferest` | https://github.com/snad-space/coniferest — isolation-forest + active learning |
| Review UI | `streamlit` | Jupyter fallback |
| Persistence | `sqlite3`, `pyarrow` | SQLite for structured records, Parquet for raw alert archive |
| Numerics & plots | `numpy`, `pandas`, `matplotlib` | baseline |
| Config | `pydantic`, `PyYAML` | validated YAML configs |

### External tool installation
- `find_orb` / `fo` — build from source or download Windows binary from Project Pluto. Requires one-time download of planetary ephemeris file (`ELP82.DAT` etc).
- `heliolinc3d` — C++ build; Windows compilation non-trivial. Fallback: run under WSL2 if native Windows build fails.

---

## 13. Milestones

| Milestone | Target | Exit criterion |
|-----------|--------|----------------|
| M0 — Accounts + plumbing | week 1 | Lasair-LSST token issued, Fink-LSST consumer pulls at least one real alert, local SQLite initialized |
| M1 — Raw ingest live | week 2 | 24-hour continuous Rubin ingest run; raw alerts in Parquet archive; ingest-time broker flags snapshotted |
| M2 — Calibration rail | week 3 | ZTF archive replay via ANTARES ingests a target window; `heliolinc3d` subprocess runs on real ZTF SSO candidates |
| M3 — Orbit-fit pipeline | week 4 | `find_orb` subprocess fits tracklets end-to-end; Marsden terms extracted; covariance captured |
| M4 — Retrospective injection harness | week 5 | V1 validation: 1I/2I recovered from ZTF archive injection under commissioning thresholds |
| M5 — 3I/ATLAS Rubin rediscovery | week 6 | V2 validation: 3I/ATLAS recovered from Rubin commissioning archive replay |
| M6 — Review UI + daily report | week 7 | Streamlit dashboard functional; daily summary generated and audited |
| M7 — Commissioning window operation | weeks 8–10 | Continuous unattended runs; distribution characterization; null-field rate characterized |
| **M8 — Threshold lock** | **2026-07-01 (target)** | `configs/thresholds-v1.yaml` committed and git-tagged; all thresholds numeric, no placeholders |
| M9 — Discovery window begins | post-lock | Any watch-list entry thereafter is subject to frozen criteria |
| M10 — Rubin SSO topic upgrade | when Fink ships it | Swap `fink_uniform_sample_lsst` for dedicated SSO topic; revalidate |
| M11 — Full LSST cadence scaling | late 2026 | Pipeline scales from ~800k → ~10M alerts/night without architectural change |

---

## 14. Risks and Open Questions

| Risk | Severity | Mitigation |
|------|----------|------------|
| Rubin SSO topic never ships on Fink | Med | Lasair-LSST custom SQL filter is the primary tap anyway; Fink is redundancy, not critical path |
| Sparse `prv_diaSources` in early ops prevents orbit fits | Med | Own-history-layer (§6 stage 3) is designed for this; linking happens at pipeline level, not broker level |
| `heliolinc3d` won't build on Windows | Med | Fall back to WSL2; both are supported environments for the project |
| `find_orb` licensing constrains sharing | Low | Personal use is fine; never redistribute without Gray's written permission |
| MPC credit reality disappoints | Low | Documented explicitly in §1; project value is candidate flagging, not credit |
| Tracklet-linking combinatorics explode at full cadence | Med | HEALPix pre-indexing + `heliolinc3d` are known to scale to LSST volume in published papers |
| Commissioning-window distributions don't stabilize by 2026-07-01 | Med | Lock date is a target, not a contract — push it out rather than lock on bad data |
| Review burden causes project abandonment | High | Auto-triage, daily summary only, expect most days empty. "No promotions" is a successful day |
| Daily review becomes adversarial (confirmation bias) | Med | Keep null-hypothesis tests (§10) mechanical; reject by checklist, not gut |
| Broker cross-match flags drift silently | Low-Med | Raw payloads snapshotted at ingest; re-query only at review time, not in pipeline logic |
| `find_orb` binary dependency is fragile | Low | Pin version; container/vendored build if necessary |

### Open questions (to resolve during M0–M2)
- Exact `heliolinc3d` input format and CLI interface on Windows/WSL2.
- Whether Lasair-LSST SQL filter API supports the motion + novelty predicates we need, or whether we need client-side post-filter.
- Whether Fink's LSST topic retention is long enough for archive replay (days vs. weeks).
- Whether the `fink_uniform_sample_lsst` sample is large enough to make redundancy meaningful.

---

## 15. Success Metrics

### Technical
- ≥ 80% recall on retrospective ISO injection (V1).
- Successful rediscovery of 3I/ATLAS from Rubin commissioning archive (V2).
- Null-field watch-list rate within pre-registered budget (V4).

### Operational
- Unattended pipeline runs for ≥ 14 consecutive nights without human intervention.
- End-to-end processing of one night's alerts completes in < 2 hours (N6).
- Audit log captures 100% of decisions.

### Scientific
- `configs/thresholds-v1.yaml` exists, is dated 2026-07-01 (±2 weeks), and is git-tagged immutable.
- At least one watch-list entry survives all null-hypothesis tests in §10 within the first 90 days of the discovery window. (Null result is also acceptable — publishing "nothing unusual detected over N nights under these criteria" is scientifically valuable per Wright et al. 2018.)
- Any external communication about the project clearly distinguishes watch-list (alert-only) from candidate (follow-up-confirmed).

### Personal sustainability
- Daily review sessions complete in < 10 minutes on nights with no promotions.
- Project is still running on 2026-10-22 (six months from PRD date).

---

## 16. Glossary and References

### Glossary
- **Alert** — packet issued by Rubin within ~60s of observation; contains astrometry, photometry, cutouts, features.
- **DIA source** — Difference-Image-Analysis detection (a point in the difference image above threshold).
- **Dark comet** — Solar System body showing non-gravitational acceleration without visible activity.
- **ISO** — Interstellar Object; unbound trajectory, e > 1.
- **Marsden terms A1, A2, A3** — radial, transverse, normal non-gravitational acceleration parameters in the Marsden-Sekanina comet force model.
- **MPC** — Minor Planet Center; clearinghouse for Solar System astrometry and orbits.
- **Tracklet** — a set of detections of the same object within one night (or linked across nights).
- **Watch-list** — alert-only flagged object requiring follow-up.
- **Candidate** — watch-list object that has survived external follow-up confirmation.

### References
- Ivezic et al. 2019, ApJ 873:111 — LSST overview
- Bellm et al. 2019, PASP 131 — ZTF
- Sánchez-Sáez et al. 2021, AJ 161 — ALeRCE
- Pruzhinskaya et al. 2019, MNRAS 489 — SNAD
- Lochner & Bassett 2021, arXiv:2010.11202 — Astronomaly
- Tyson et al. 2020, AJ 160 — LSST satellite mitigation
- Seligman et al. 2023, ApJ 162:229 — dark comets as a class
- Jewitt & Seligman 2023, ARA&A — ISO review
- Micheli et al. 2018, Nature 559:223 — 'Oumuamua non-grav
- Hoover et al. 2022, PSJ 3:71 — Rubin ISO yield
- Marceta & Seligman 2023, PSJ 4:238 — ISO detectability
- Bergner & Seligman 2023, Nature 615:610 — 'Oumuamua H2
- Sheikh 2020, IJA 19:237 — Nine Axes of Merit
- Wright et al. 2018, arXiv:1809.06857 — publishing technosignature negatives
- Holman et al. 2018 / Heinze et al. 2022 — HelioLinC3D
- MPEC 2025-N12 (2 July 2025) — 3I/ATLAS discovery
- arXiv:2507.13409 — Rubin commissioning observations of 3I/ATLAS

### Broker and tool docs
- Rubin data products: https://rubinobservatory.org/for-scientists/data-products
- Alert schema: https://github.com/lsst/alert_packet
- APDB schema: https://sdm-schemas.lsst.io/apdb.html
- Fink LSST livestream: https://doc.lsst.fink-broker.org/services/livestream/
- Fink portal: https://lsst.fink-portal.org
- Fink filter source: https://github.com/astrolabsoftware/fink-filters
- Lasair-LSST: https://lasair.lsst.ac.uk
- Lasair FAQ: https://lasair.readthedocs.io/en/main/more_info/faqs.html
- ANTARES archive: https://antares.noirlab.edu
- MPC Explorer: https://www.minorplanetcenter.net/db_search
- ADES format: https://minorplanetcenter.net/iau/info/IAU2015_ADES.pdf
- find_orb: https://www.projectpluto.com/find_orb.htm
- heliolinc3d: https://github.com/lsst-dm/heliolinc2
- SNAD coniferest: https://github.com/snad-space/coniferest
- sbpy: https://sbpy.readthedocs.io

---

## 17. Out of Scope (explicit)

- UAP / UFO detection of any kind. Rubin is architecturally wrong for low-altitude atmospheric phenomena.
- Follow-up telescope scheduling or operation.
- Coordination with professional surveys or observatories beyond public data consumption.
- Any analysis requiring Rubin Science Platform, Butler, or pixel-level data access.
- Alert service for external users.
- Open-source distribution of `find_orb`, proprietary ephemerides, or rights-holder-restricted Rubin data.
- Publication claims not based on follow-up-confirmed candidates.

---

*End of PRD v0.1. Changes after threshold lock require a version bump and a new lock date.*
