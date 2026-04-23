# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A personal-scale anomaly-detection pipeline over the Vera C. Rubin Observatory (LSST) public alert stream. Primary target: dark comets (Seligman et al. 2023). Secondary target: interstellar objects. Single-machine, Windows 11, Python. See `PRD.md` for full requirements.

## Current state

Pre-implementation. Only documentation exists:

- `PRD.md` — full product requirements document
- `docs/decisions/` — architecture decision records (ADRs) explaining *why* each commitment was made
- `docs/decisions/README.md` — index of decisions
- `docs/decisions/template.md` — template for new ADRs

No source code yet. Implementation begins with milestone M0 in PRD §13.

## Source of truth

Two locations, two purposes:

- **`PRD.md`** — what the system is and does. The spec.
- **`docs/decisions/*.md`** — why it is that way. The history of choices and the reasoning each closed.

If PRD requirements appear to conflict with code behavior, the PRD wins until a new ADR supersedes. If you're about to make a load-bearing decision that has no ADR, **write the ADR first**, then commit code.

## Invariants — silent-break risks

Do not violate these without first writing a new ADR that explicitly supersedes the relevant one:

1. **Two-stage gate.** Alert-only outputs are always "watch-list." "Candidate" status requires external follow-up astrometry. Never conflate or publish watch-list as candidate. (ADR-0005)
2. **Threshold lock is dated and git-tagged.** `configs/thresholds-v1.yaml` is immutable after the lock date. Changes require a new tagged version (`-v2.yaml`), not an edit-in-place. (ADR-0006)
3. **`find_orb` is personal-use only.** Do not include its binaries, source, or derived ephemerides in this repo. Do not redistribute under any circumstance. If the project ever becomes OSS, this ADR must be revisited. (ADR-0008)
4. **Raw alert payloads persist verbatim at ingest.** Broker cross-match flags are snapshotted at ingest and never re-queried in place. Reproducibility depends on this. (PRD §6, §8 N5; ADR-0009)
5. **No pixel-level Rubin data.** Project is alert-stream-only. RSP / Butler / DP1 are out of scope — we are not a data-rights holder. (ADR-0010)
6. **Dark comets primary, ISOs secondary.** Do not refactor the pipeline to treat ISOs as primary; the physics of alert-only orbit closure makes ISO-primary infeasible. (ADR-0004)
7. **Rubin primary, ZTF calibration-only.** ZTF data never drives a watch-list promotion. (ADR-0003)

## Decision-record maintenance protocol

**When to add an ADR:**

- Any decision that would surprise a future reader of the code if not documented.
- Any choice between substantive alternatives.
- Any override or amendment of an existing ADR.

**How:**

1. Copy `docs/decisions/template.md` to `docs/decisions/NNNN-short-title.md` (next sequential number — check the index for the current max).
2. Fill in context, decision, consequences, alternatives considered, references.
3. If it supersedes an earlier ADR, mark the old one **"Superseded by ADR-NNNN"** in its Status field and link forward.
4. Add a one-line entry to `docs/decisions/README.md`.
5. Commit ADR and index together in the same commit.

**Rule:** never edit an accepted ADR in place except to mark it superseded. Correctness of the historical record matters more than brevity. If the reasoning changes, write a new ADR — do not rewrite history.

## Useful pointers

External docs referenced throughout the project:

- `find_orb`: https://www.projectpluto.com/find_orb.htm
- `heliolinc3d`: https://github.com/lsst-dm/heliolinc2
- Fink LSST portal: https://lsst.fink-portal.org
- Lasair-LSST: https://lasair.lsst.ac.uk
- Rubin alert schema: https://github.com/lsst/alert_packet
- APDB schema: https://sdm-schemas.lsst.io/apdb.html
- 3I/ATLAS Rubin commissioning paper: arXiv:2507.13409 (validation target)
- MPC Explorer: https://www.minorplanetcenter.net/db_search

## Once implementation begins

This section is a placeholder; populate when code lands.

- Build / install commands
- How to run the pipeline for a single night's alerts
- How to run a specific test (single pytest invocation)
- How to run the retrospective injection harness
- How to replay archived Rubin or ZTF alerts
- Where the detection DB and raw alert archive live on disk
- Architecture notes for non-obvious subsystems: tracklet-linking subprocess wrapper, `find_orb` subprocess wrapper, HEALPix bucketing scheme, broker-flag snapshot semantics
