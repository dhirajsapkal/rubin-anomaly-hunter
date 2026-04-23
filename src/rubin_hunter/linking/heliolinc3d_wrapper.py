"""Subprocess wrapper around heliolinc3d for tracklet linking.

This module delegates tracklet linking to the external `heliolinc3d` C++
binary per ADR-0007 — we never reimplement tree-based / Kubica-style
linking in Python. The wrapper provides:

  * A Windows-native invocation path, with a WSL2 fallback (PRD §12, §14).
  * A mock mode for development when the binary is unavailable: it performs
    trivial same-night motion-consistent grouping so the rest of the
    pipeline can run end-to-end. Mock output is not scientifically valid
    and is loudly flagged at runtime.

References
----------
- ADR-0007 (docs/decisions/0007-delegate-tracklet-linking.md)
- Heinze et al. 2022 (HelioLinC3D)
- https://github.com/lsst-dm/heliolinc2
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass
class Tracklet:
    """A linked set of detections believed to be the same moving object.

    Field names map onto the `tracklets` table produced by the data-layer
    agent. If that schema differs, only the DB-write path needs to change;
    the linker output format stays the same.
    """

    tracklet_id: str
    detection_ids: list[int]
    n_detections: int
    n_nights: int
    mjd_start: float
    mjd_end: float
    mean_ra_deg: float
    mean_dec_deg: float
    # Rough sky-plane motion in arcsec/hour, averaged over the tracklet.
    mean_motion_arcsec_hr: float
    quality_flag: str  # "ok", "suspect", "mock"
    source: str  # "heliolinc3d" or "mock"
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


DEFAULT_HELIOLINC_ENV = "HELIOLINC3D_PATH"


class HelioLinC3DRunner:
    """Invoke heliolinc3d as a subprocess (ADR-0007).

    Parameters
    ----------
    binary_path
        Path to the `heliolinc` or `heliolinc3d` executable. If None we
        consult the ``HELIOLINC3D_PATH`` env var, then ``shutil.which``.
        When nothing is found we degrade to mock mode.
    work_dir
        Scratch directory for input/output files. A temp dir is created
        per-call if None.
    use_wsl
        If True, invoke the binary through ``wsl.exe`` so a Linux build
        can be used from a Windows host. See PRD §12 / ADR-0007.
    mock_if_missing
        If True and no binary is found, run in mock mode (default True).
        Set False to raise instead — useful for production guards.
    """

    def __init__(
        self,
        binary_path: Path | None = None,
        work_dir: Path | None = None,
        *,
        use_wsl: bool = False,
        mock_if_missing: bool = True,
    ) -> None:
        self.binary_path = self._resolve_binary(binary_path)
        self.work_dir = Path(work_dir) if work_dir is not None else None
        self.use_wsl = use_wsl
        self.mock_if_missing = mock_if_missing
        self._mock_mode = self.binary_path is None

        if self._mock_mode:
            if not self.mock_if_missing:
                raise FileNotFoundError(
                    "heliolinc3d binary not found and mock_if_missing=False. "
                    "Install heliolinc3d or set HELIOLINC3D_PATH."
                )
            logger.warning(
                "=" * 72 + "\n"
                "HelioLinC3DRunner: MOCK MODE ENABLED\n"
                "heliolinc3d binary not found on PATH or via HELIOLINC3D_PATH.\n"
                "Falling back to trivial same-night motion-consistent grouping.\n"
                "RESULTS ARE NOT SCIENTIFICALLY VALID. Do not use for science.\n"
                + "=" * 72
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def link_detections(
        self,
        detections: pd.DataFrame,
        params: dict | None = None,
    ) -> list[Tracklet]:
        """Link detections into tracklets.

        Parameters
        ----------
        detections
            DataFrame with at least: ``detection_id`` (int),
            ``mjd`` (float), ``ra_deg`` (float), ``dec_deg`` (float),
            ``mag`` (float, optional), ``filter`` (str, optional).
            Extra columns are ignored but passed through to the tool.
        params
            Optional dict of heliolinc3d tuning parameters (max_v,
            min_obs, mintrkpts, etc). Merged with defaults.

        Returns
        -------
        list[Tracklet]
        """
        self._validate_detections(detections)
        merged_params = self._default_params()
        if params:
            merged_params.update(params)

        if self._mock_mode:
            return self._mock_link(detections, merged_params)
        return self._run_real(detections, merged_params)

    # ------------------------------------------------------------------
    # Real invocation
    # ------------------------------------------------------------------

    def _run_real(self, detections: pd.DataFrame, params: dict) -> list[Tracklet]:
        scratch_ctx: tempfile.TemporaryDirectory[str] | None = None
        if self.work_dir is not None:
            self.work_dir.mkdir(parents=True, exist_ok=True)
            root = self.work_dir
        else:
            scratch_ctx = tempfile.TemporaryDirectory(prefix="heliolinc3d_")
            root = Path(scratch_ctx.name)

        try:
            in_path = root / "detections.csv"
            out_path = root / "tracklets.json"
            detections.to_csv(in_path, index=False)

            cmd = self._build_cmd(in_path, out_path, params)
            logger.info("Running heliolinc3d: %s", " ".join(cmd))
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=params.get("timeout_s", 3600),
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"heliolinc3d failed (rc={result.returncode}):\n"
                    f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
                )
            if not out_path.exists():
                raise RuntimeError(
                    "heliolinc3d produced no output file; check params."
                )
            return self._parse_output(out_path, detections)
        finally:
            if scratch_ctx is not None:
                scratch_ctx.cleanup()

    def _build_cmd(
        self, in_path: Path, out_path: Path, params: dict
    ) -> list[str]:
        """Build the CLI invocation.

        NOTE: heliolinc3d's real CLI has evolved; confirm flags against the
        installed version (lsst-dm/heliolinc2). The arg list below is a
        reasonable placeholder; override via `params['cli_args']` to pass
        the exact flags your build expects.
        """
        if "cli_args" in params:
            base = [str(self.binary_path), *params["cli_args"]]
        else:
            base = [
                str(self.binary_path),
                "--input",
                str(in_path),
                "--output",
                str(out_path),
                "--min-obs",
                str(params["min_obs"]),
                "--max-vel",
                str(params["max_velocity_deg_per_day"]),
            ]
        if self.use_wsl:
            # Translate the binary path into a WSL-visible form.
            return ["wsl.exe", *base]
        return base

    def _parse_output(
        self, out_path: Path, detections: pd.DataFrame
    ) -> list[Tracklet]:
        with out_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        tracklets: list[Tracklet] = []
        by_id = detections.set_index("detection_id")
        for entry in payload.get("tracklets", []):
            det_ids: list[int] = list(entry["detection_ids"])
            rows = by_id.loc[det_ids]
            tracklets.append(self._build_tracklet(entry["tracklet_id"], det_ids, rows, "heliolinc3d"))
        return tracklets

    # ------------------------------------------------------------------
    # Mock mode
    # ------------------------------------------------------------------

    def _mock_link(
        self, detections: pd.DataFrame, params: dict
    ) -> list[Tracklet]:
        """Trivial grouping: within each night, greedy-chain detections
        whose pairwise rate is below a motion cap and spatially close.

        This exists so downstream stages (orbit fit, scoring, gate) can
        demo end-to-end. It is NOT a linker.
        """
        if detections.empty:
            return []

        max_motion_deg_per_day = params.get("max_velocity_deg_per_day", 2.0)
        min_obs = params.get("min_obs", 2)
        night_bin_days = params.get("night_bin_days", 1.0)

        work = detections.copy()
        work["night"] = np.floor(work["mjd"].to_numpy() / night_bin_days).astype(int)
        work = work.sort_values(["night", "mjd"]).reset_index(drop=True)

        tracklets: list[Tracklet] = []
        counter = 0

        for night, chunk in work.groupby("night"):
            used: set[int] = set()
            rows = chunk.to_dict("records")
            for i, seed in enumerate(rows):
                if i in used:
                    continue
                group_idx = [i]
                cur = seed
                for j in range(i + 1, len(rows)):
                    if j in used:
                        continue
                    cand = rows[j]
                    dt = cand["mjd"] - cur["mjd"]
                    if dt <= 0:
                        continue
                    dra = (cand["ra_deg"] - cur["ra_deg"]) * np.cos(
                        np.deg2rad(cur["dec_deg"])
                    )
                    ddec = cand["dec_deg"] - cur["dec_deg"]
                    sep_deg = float(np.hypot(dra, ddec))
                    rate_deg_per_day = sep_deg / dt
                    if rate_deg_per_day <= max_motion_deg_per_day:
                        group_idx.append(j)
                        cur = cand
                if len(group_idx) >= min_obs:
                    det_ids = [rows[k]["detection_id"] for k in group_idx]
                    used.update(group_idx)
                    sub = chunk.iloc[group_idx]
                    counter += 1
                    tid = f"mock-{int(night)}-{counter:05d}"
                    tracklets.append(
                        self._build_tracklet(tid, det_ids, sub, "mock", quality="mock")
                    )
        return tracklets

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_detections(df: pd.DataFrame) -> None:
        required = {"detection_id", "mjd", "ra_deg", "dec_deg"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"detections DataFrame is missing columns: {missing}")

    @staticmethod
    def _default_params() -> dict:
        return {
            "min_obs": 2,
            "max_velocity_deg_per_day": 2.0,
            "night_bin_days": 1.0,
            "timeout_s": 3600,
        }

    @staticmethod
    def _resolve_binary(binary_path: Path | None) -> Path | None:
        if binary_path is not None:
            p = Path(binary_path)
            return p if p.exists() else None
        env_val = os.environ.get(DEFAULT_HELIOLINC_ENV)
        if env_val and Path(env_val).exists():
            return Path(env_val)
        for name in ("heliolinc", "heliolinc3d", "heliolinc.exe", "heliolinc3d.exe"):
            found = shutil.which(name)
            if found:
                return Path(found)
        return None

    @staticmethod
    def _build_tracklet(
        tracklet_id: str,
        detection_ids: list[int],
        rows: pd.DataFrame,
        source: str,
        quality: str = "ok",
    ) -> Tracklet:
        mjd = rows["mjd"].to_numpy()
        mjd_start, mjd_end = float(mjd.min()), float(mjd.max())
        arc_days = max(mjd_end - mjd_start, 0.0)
        n_nights = int(np.floor(arc_days) + 1) if len(mjd) else 0

        # crude sky-plane rate (arcsec / hour)
        if len(rows) >= 2 and arc_days > 0:
            ra = rows["ra_deg"].to_numpy()
            dec = rows["dec_deg"].to_numpy()
            dra = (ra[-1] - ra[0]) * np.cos(np.deg2rad(np.mean(dec)))
            ddec = dec[-1] - dec[0]
            sep_arcsec = float(np.hypot(dra, ddec) * 3600.0)
            mean_motion = sep_arcsec / (arc_days * 24.0)
        else:
            mean_motion = 0.0

        return Tracklet(
            tracklet_id=str(tracklet_id),
            detection_ids=list(detection_ids),
            n_detections=len(detection_ids),
            n_nights=n_nights,
            mjd_start=mjd_start,
            mjd_end=mjd_end,
            mean_ra_deg=float(np.mean(rows["ra_deg"])),
            mean_dec_deg=float(np.mean(rows["dec_deg"])),
            mean_motion_arcsec_hr=float(mean_motion),
            quality_flag=quality,
            source=source,
        )

    @property
    def is_mock(self) -> bool:
        return self._mock_mode
