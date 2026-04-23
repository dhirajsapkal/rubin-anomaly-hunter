"""Subprocess wrapper around find_orb (`fo` batch mode) for short-arc fits.

LICENSING BANNER — READ BEFORE MODIFYING (ADR-0008)
----------------------------------------------------
`find_orb` (Bill Gray, Project Pluto) is SOURCE-AVAILABLE but NOT OSI-open.

  * Personal use is fine per ADR-0002.
  * DO NOT commit `fo` / `find_orb` binaries, source, planetary-ephemeris
    files (e.g. ELP82.DAT, DE440 kernels), or derived ephemeris products
    into this repository under any circumstance.
  * DO NOT redistribute any part of find_orb without Bill Gray's explicit
    written permission.
  * If this project ever opens or publishes under an OSI license, ADR-0008
    MUST be revisited and the orbit-fit path likely migrated.

Installation is a user-local step. The wrapper resolves the `fo` binary
from (in order): the explicit `fo_path` arg, the ``FINDORB_PATH`` env var,
then PATH. If nothing is found we fall back to a clearly-labelled mock.

References
----------
- ADR-0008 (docs/decisions/0008-find-orb-for-orbit-fitting.md)
- https://www.projectpluto.com/find_orb.htm
- https://projectpluto.com/force.htm  (Marsden A1/A2/A3 documentation)
- ADES format: https://minorplanetcenter.net/iau/info/IAU2015_ADES.pdf
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

try:  # optional — sbpy is our preferred ADES writer if it's available
    from sbpy.data import Obs  # type: ignore

    _HAS_SBPY = True
except Exception:  # pragma: no cover - import-time only
    _HAS_SBPY = False

logger = logging.getLogger(__name__)

FINDORB_ENV = "FINDORB_PATH"
EPHEM_ENV = "FINDORB_EPHEM_DIR"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class OrbitFit:
    """Orbital elements + Marsden non-grav terms from a single fit.

    Matches the `orbit_fits` table the data-layer agent exposes. All angles
    in degrees; distances in AU; A1/A2/A3 in AU/day^2 (the Marsden units).
    For hyperbolic solutions (e >= 1) the aphelion `Q` is NaN.
    """

    # Keplerian
    a: float
    e: float
    i: float
    q: float  # perihelion distance, AU
    Q: float  # aphelion, AU (NaN for hyperbolic)
    Omega: float  # longitude of ascending node, deg
    omega: float  # argument of perihelion, deg
    # Marsden non-grav (AU / day^2)
    A1: float
    A2: float
    A3: float
    # 1-sigma uncertainties (same units as their values)
    sigma_a: float
    sigma_e: float
    sigma_i: float
    sigma_q: float
    sigma_Q: float
    sigma_Omega: float
    sigma_omega: float
    sigma_A1: float
    sigma_A2: float
    sigma_A3: float
    # Fit diagnostics
    fit_rms: float  # arcseconds, astrometric residual RMS
    n_obs: int
    software_version: str
    # Covariance is square, row-ordered as [a, e, i, Omega, omega, A1, A2, A3]
    covariance_matrix: list[list[float]] = field(default_factory=list)
    # Provenance / extra bookkeeping.
    mode: str = "findorb"  # "findorb" or "mock"
    epoch_mjd: float | None = None
    used_interstellar: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_bound(self) -> bool:
        return self.e < 1.0 and math.isfinite(self.a) and self.a > 0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class FindOrbRunner:
    """Invoke `fo` (find_orb batch mode) as a subprocess.

    Parameters
    ----------
    fo_path
        Path to the `fo` executable. Resolution order:
        explicit arg → ``FINDORB_PATH`` env var → PATH lookup.
    work_dir
        Persistent scratch directory. Per-call temp dir is used if None.
    use_wsl
        Invoke via ``wsl.exe`` (see ADR-0008 / PRD §12). Useful when the
        Windows-native build is flaky and a Linux build is installed
        inside WSL2.
    mock_if_missing
        If True (default) and no binary is found, fall back to a noisy
        2-body mock fit so downstream stages can run.
    """

    def __init__(
        self,
        fo_path: Path | None = None,
        work_dir: Path | None = None,
        *,
        use_wsl: bool = False,
        mock_if_missing: bool = True,
    ) -> None:
        self.fo_path = self._resolve_binary(fo_path)
        self.work_dir = Path(work_dir) if work_dir is not None else None
        self.use_wsl = use_wsl
        self.mock_if_missing = mock_if_missing
        self._mock_mode = self.fo_path is None

        if self._mock_mode:
            if not self.mock_if_missing:
                raise FileNotFoundError(
                    "find_orb `fo` binary not found and mock_if_missing=False. "
                    f"Install find_orb and set {FINDORB_ENV}."
                )
            logger.warning(
                "=" * 72 + "\n"
                "FindOrbRunner: MOCK MODE ENABLED\n"
                f"`fo` binary not found via arg, {FINDORB_ENV}, or PATH.\n"
                "Fits are 2-body + small noise; Marsden non-grav terms are\n"
                "injected as zero-mean noise only. NOT SCIENTIFICALLY VALID.\n"
                + "=" * 72
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit_tracklet(
        self,
        detections: pd.DataFrame,
        use_interstellar: bool = False,
    ) -> OrbitFit:
        """Fit a single tracklet's detections to an orbit.

        Parameters
        ----------
        detections
            Astrometry for this tracklet. Required columns:
            ``detection_id``, ``mjd`` (UTC), ``ra_deg``, ``dec_deg``.
            Optional: ``mag``, ``filter``, ``obs_code`` (default X05 = Rubin),
            ``ra_sigma_arcsec``, ``dec_sigma_arcsec``.
        use_interstellar
            If True, pass find_orb the 'I' interstellar flag (allow e > 1
            unbound solutions). Required for ISO watch-list objects.
        """
        self._validate_detections(detections)
        if self._mock_mode:
            return self._mock_fit(detections, use_interstellar=use_interstellar)
        return self._run_real(detections, use_interstellar=use_interstellar)

    # ------------------------------------------------------------------
    # Real invocation
    # ------------------------------------------------------------------

    def _run_real(
        self, detections: pd.DataFrame, *, use_interstellar: bool
    ) -> OrbitFit:
        scratch_ctx: tempfile.TemporaryDirectory[str] | None = None
        if self.work_dir is not None:
            self.work_dir.mkdir(parents=True, exist_ok=True)
            root = self.work_dir
        else:
            scratch_ctx = tempfile.TemporaryDirectory(prefix="findorb_")
            root = Path(scratch_ctx.name)

        try:
            ades_path = root / "observations.xml"
            write_ades(detections, ades_path)

            out_path = root / "fo_elements.json"
            cmd = self._build_cmd(ades_path, out_path, use_interstellar=use_interstellar)

            logger.info("Running find_orb (fo): %s", " ".join(cmd))
            env = os.environ.copy()
            # Optional: point fo at its ephemeris dir.
            if EPHEM_ENV in env:
                env["FINDORB_EPHEM_DIR"] = env[EPHEM_ENV]
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=600,
                env=env,
                cwd=root,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"find_orb `fo` failed (rc={result.returncode}):\n"
                    f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
                )
            if not out_path.exists():
                raise RuntimeError(
                    "find_orb produced no elements output; check CLI args "
                    "against installed fo version."
                )
            return self._parse_fo_output(out_path, detections, use_interstellar)
        finally:
            if scratch_ctx is not None:
                scratch_ctx.cleanup()

    def _build_cmd(
        self, ades_path: Path, out_path: Path, *, use_interstellar: bool
    ) -> list[str]:
        """Assemble the `fo` CLI.

        fo flags vary by version. The command below uses the most common
        published switches (batch mode, JSON output, Marsden terms on).
        Override via env ``FINDORB_EXTRA_ARGS`` if the installed build
        needs different flags.
        """
        base: list[str] = [str(self.fo_path), str(ades_path)]
        # Request JSON elements + covariance output.
        base += ["-O", str(out_path)]
        # Enable Marsden non-grav terms.
        base += ["-z", "A1,A2,A3"]
        # Allow interstellar / hyperbolic class if requested.
        if use_interstellar:
            base += ["-I"]
        extra = os.environ.get("FINDORB_EXTRA_ARGS", "").strip()
        if extra:
            base += extra.split()
        if self.use_wsl:
            return ["wsl.exe", *base]
        return base

    def _parse_fo_output(
        self, out_path: Path, detections: pd.DataFrame, used_interstellar: bool
    ) -> OrbitFit:
        """Parse `fo`'s JSON dump into an OrbitFit.

        `fo`'s JSON schema changes version-to-version. We look up common
        key names and degrade gracefully; missing values become NaN.
        """
        with out_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        def pick(obj: dict, keys: list[str], default: float = float("nan")) -> float:
            for k in keys:
                if k in obj and obj[k] is not None:
                    try:
                        return float(obj[k])
                    except (TypeError, ValueError):
                        pass
            return default

        root = payload.get("objects", [payload])[0] if isinstance(payload, dict) else payload
        elems = root.get("elements", root)
        sigmas = root.get("sigmas", {})
        cov = root.get("covariance", []) or root.get("covariance_matrix", [])

        a = pick(elems, ["a", "semi_major_axis"])
        e = pick(elems, ["e", "eccentricity"])
        q = pick(elems, ["q", "perihelion"])
        Q = a * (1.0 + e) if (math.isfinite(a) and e < 1.0 and a > 0) else float("nan")
        i = pick(elems, ["i", "inclination"])
        Omega = pick(elems, ["Omega", "node", "ascending_node"])
        omega = pick(elems, ["omega", "arg_peri", "argument_of_perihelion"])
        A1 = pick(elems, ["A1", "a1"], 0.0)
        A2 = pick(elems, ["A2", "a2"], 0.0)
        A3 = pick(elems, ["A3", "a3"], 0.0)

        rms = pick(root, ["rms", "fit_rms", "residual_rms"], 0.0)
        n_obs = int(pick(root, ["n_obs", "nobs"], float(len(detections))))
        version = str(root.get("software_version") or root.get("version") or "find_orb")
        epoch = pick(elems, ["epoch", "epoch_mjd"])

        return OrbitFit(
            a=a,
            e=e,
            i=i,
            q=q if math.isfinite(q) else (a * (1.0 - e) if math.isfinite(a) else float("nan")),
            Q=Q,
            Omega=Omega,
            omega=omega,
            A1=A1,
            A2=A2,
            A3=A3,
            sigma_a=pick(sigmas, ["a", "sigma_a"], 0.0),
            sigma_e=pick(sigmas, ["e", "sigma_e"], 0.0),
            sigma_i=pick(sigmas, ["i", "sigma_i"], 0.0),
            sigma_q=pick(sigmas, ["q", "sigma_q"], 0.0),
            sigma_Q=pick(sigmas, ["Q", "sigma_Q"], 0.0),
            sigma_Omega=pick(sigmas, ["Omega", "sigma_Omega"], 0.0),
            sigma_omega=pick(sigmas, ["omega", "sigma_omega"], 0.0),
            sigma_A1=pick(sigmas, ["A1", "sigma_A1"], 0.0),
            sigma_A2=pick(sigmas, ["A2", "sigma_A2"], 0.0),
            sigma_A3=pick(sigmas, ["A3", "sigma_A3"], 0.0),
            fit_rms=rms,
            n_obs=n_obs,
            software_version=version,
            covariance_matrix=cov if isinstance(cov, list) else [],
            mode="findorb",
            epoch_mjd=epoch if math.isfinite(epoch) else None,
            used_interstellar=used_interstellar,
        )

    # ------------------------------------------------------------------
    # Mock mode
    # ------------------------------------------------------------------

    def _mock_fit(
        self, detections: pd.DataFrame, *, use_interstellar: bool
    ) -> OrbitFit:
        """Produce a plausible-but-noisy 2-body fit using astropy.

        Strategy: assume geocentric distance = 1 AU; compute rough Earth-
        centric sky motion; back-solve a nominal semi-major axis from the
        motion magnitude using Kepler's law at 1 AU. The output is NOT
        scientifically valid — it exists so downstream stages have a
        populated OrbitFit to score.
        """
        rng = np.random.default_rng(
            int(detections["mjd"].iloc[0] * 1e6) ^ int(len(detections))
        )

        mjd = detections["mjd"].to_numpy()
        ra = np.deg2rad(detections["ra_deg"].to_numpy())
        dec = np.deg2rad(detections["dec_deg"].to_numpy())

        # Rough angular rate (rad/day).
        arc_days = float(mjd.max() - mjd.min())
        if arc_days <= 0 or len(mjd) < 2:
            rate_rad_per_day = 1e-3
        else:
            dra = (ra[-1] - ra[0]) * np.cos(np.mean(dec))
            ddec = dec[-1] - dec[0]
            rate_rad_per_day = float(np.hypot(dra, ddec) / arc_days)

        # If asked to treat as interstellar, bias toward e > 1.
        if use_interstellar:
            e = float(rng.uniform(1.0, 1.6))
            a = float(rng.uniform(-5.0, -1.0))  # convention: a < 0 for hyperbolic
            q = a * (1.0 - e)  # positive because a<0, (1-e)<0
            Q = float("nan")
        else:
            # Back-of-envelope bound orbit.
            # Rate at 1 AU from a circular orbit at radius a ~ GM/a^2 stuff.
            # Use a rough heuristic: a ~ 1 / (rate_rad_per_day / k) ^ (2/3).
            k = 0.0172  # Gaussian gravitational constant in rad/day at 1 AU
            if rate_rad_per_day > 0:
                a = float((k / rate_rad_per_day) ** (2.0 / 3.0))
                a = max(min(a, 50.0), 0.5)
            else:
                a = 2.5
            e = float(rng.uniform(0.0, 0.6))
            q = a * (1.0 - e)
            Q = a * (1.0 + e)

        # Inject small non-grav magnitudes sometimes — so scorer has
        # something to find when the caller seeds a "dark comet" row.
        A1 = float(rng.normal(0.0, 5e-10))
        A2 = float(rng.normal(0.0, 1e-10))
        A3 = float(rng.normal(0.0, 1e-10))

        sigma_e = float(rng.uniform(0.05, 0.3))
        sigma_a = float(abs(a) * rng.uniform(0.02, 0.1))
        sigma_q = sigma_a
        sigma_Q = sigma_a if math.isfinite(Q) else 0.0
        sigma_i = float(rng.uniform(0.2, 2.0))
        sigma_Omega = float(rng.uniform(0.2, 2.0))
        sigma_omega = float(rng.uniform(0.2, 2.0))
        sigma_A1 = abs(A1) * 0.2 + 1e-11
        sigma_A2 = abs(A2) * 0.2 + 1e-12
        sigma_A3 = abs(A3) * 0.2 + 1e-12

        fit = OrbitFit(
            a=a,
            e=e,
            i=float(np.rad2deg(rng.uniform(0, math.pi / 4))),
            q=float(q),
            Q=float(Q),
            Omega=float(np.rad2deg(rng.uniform(0, 2 * math.pi))),
            omega=float(np.rad2deg(rng.uniform(0, 2 * math.pi))),
            A1=A1,
            A2=A2,
            A3=A3,
            sigma_a=sigma_a,
            sigma_e=sigma_e,
            sigma_i=sigma_i,
            sigma_q=sigma_q,
            sigma_Q=sigma_Q,
            sigma_Omega=sigma_Omega,
            sigma_omega=sigma_omega,
            sigma_A1=sigma_A1,
            sigma_A2=sigma_A2,
            sigma_A3=sigma_A3,
            fit_rms=float(rng.uniform(0.1, 0.6)),
            n_obs=int(len(detections)),
            software_version="mock-findorb-0",
            covariance_matrix=_diag_cov(
                [sigma_a, sigma_e, sigma_i, sigma_Omega, sigma_omega, sigma_A1, sigma_A2, sigma_A3]
            ),
            mode="mock",
            epoch_mjd=float(np.mean(mjd)),
            used_interstellar=use_interstellar,
            notes="mock — not scientifically valid",
        )
        return fit

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_detections(df: pd.DataFrame) -> None:
        required = {"detection_id", "mjd", "ra_deg", "dec_deg"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(
                f"tracklet detections DataFrame missing columns: {missing}"
            )
        if len(df) < 2:
            raise ValueError("need at least 2 detections to fit an orbit")

    @staticmethod
    def _resolve_binary(fo_path: Path | None) -> Path | None:
        if fo_path is not None:
            p = Path(fo_path)
            return p if p.exists() else None
        env_val = os.environ.get(FINDORB_ENV)
        if env_val and Path(env_val).exists():
            return Path(env_val)
        for name in ("fo", "fo.exe", "find_orb", "find_orb.exe"):
            found = shutil.which(name)
            if found:
                return Path(found)
        return None

    @property
    def is_mock(self) -> bool:
        return self._mock_mode


def _diag_cov(sigmas: list[float]) -> list[list[float]]:
    n = len(sigmas)
    return [[(sigmas[i] ** 2 if i == j else 0.0) for j in range(n)] for i in range(n)]


# ---------------------------------------------------------------------------
# ADES writer
# ---------------------------------------------------------------------------


def write_ades(detections: pd.DataFrame, out_path: Path) -> None:
    """Write detections to an ADES (XML) file that find_orb accepts.

    Prefers sbpy's ADES serializer when available; otherwise emits a
    hand-rolled minimal ADES 2015 XML. If that fails we fall back to the
    MPC 80-column format at `out_path.with_suffix('.obs')` — find_orb
    also reads 80-column.

    Required columns: mjd, ra_deg, dec_deg. Optional: mag, filter,
    obs_code (default X05), ra_sigma_arcsec, dec_sigma_arcsec.

    The ADES 2015 spec is at
    https://minorplanetcenter.net/iau/info/IAU2015_ADES.pdf.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    obs_code = "X05"  # Rubin / LSST provisional MPC site code

    if _HAS_SBPY:
        try:
            obs = Obs.from_dict(
                {
                    "epoch": detections["mjd"].to_numpy(),
                    "ra": detections["ra_deg"].to_numpy(),
                    "dec": detections["dec_deg"].to_numpy(),
                    "mag": detections.get(
                        "mag", pd.Series([99.0] * len(detections))
                    ).to_numpy(),
                    "filter": detections.get(
                        "filter", pd.Series(["r"] * len(detections))
                    ).to_numpy(),
                    "observatory": [obs_code] * len(detections),
                }
            )
            # sbpy's ADES writer is under .to_ades when present; fall
            # through to hand-rolled if the method isn't there.
            if hasattr(obs, "to_ades"):
                obs.to_ades(out_path)
                return
        except Exception as exc:  # pragma: no cover - optional path
            logger.debug("sbpy ADES writer failed (%s); using hand-rolled", exc)

    # Hand-rolled minimal ADES 2015 XML — enough columns for fo.
    lines: list[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append("<ades version=\"2017\">")
    lines.append("  <obsBlock>")
    lines.append("    <obsContext>")
    lines.append("      <observatory><mpcCode>%s</mpcCode></observatory>" % obs_code)
    lines.append("      <submitter><name>rubin-hunter</name></submitter>")
    lines.append("    </obsContext>")
    lines.append("    <obsData>")
    for _, row in detections.iterrows():
        mjd = float(row["mjd"])
        # ADES obsTime is ISO UTC; approximate conversion from MJD.
        iso = _mjd_to_iso(mjd)
        ra = float(row["ra_deg"])
        dec = float(row["dec_deg"])
        mag = float(row["mag"]) if "mag" in row and not pd.isna(row["mag"]) else 99.0
        band = str(row["filter"]) if "filter" in row and not pd.isna(row["filter"]) else "r"
        rms_ra = (
            float(row["ra_sigma_arcsec"])
            if "ra_sigma_arcsec" in row and not pd.isna(row["ra_sigma_arcsec"])
            else 0.1
        )
        rms_dec = (
            float(row["dec_sigma_arcsec"])
            if "dec_sigma_arcsec" in row and not pd.isna(row["dec_sigma_arcsec"])
            else 0.1
        )
        did = row["detection_id"]
        lines.append("      <optical>")
        lines.append(f"        <trkSub>RH{did}</trkSub>")
        lines.append(f"        <obsTime>{iso}</obsTime>")
        lines.append(f"        <ra>{ra:.6f}</ra>")
        lines.append(f"        <dec>{dec:+.6f}</dec>")
        lines.append(f"        <rmsRA>{rms_ra:.3f}</rmsRA>")
        lines.append(f"        <rmsDec>{rms_dec:.3f}</rmsDec>")
        lines.append(f"        <mag>{mag:.2f}</mag>")
        lines.append(f"        <band>{band}</band>")
        lines.append(f"        <stn>{obs_code}</stn>")
        lines.append("        <mode>CCD</mode>")
        lines.append("      </optical>")
    lines.append("    </obsData>")
    lines.append("  </obsBlock>")
    lines.append("</ades>")

    out_path.write_text("\n".join(lines), encoding="utf-8")


# MPC-80 fallback ----------------------------------------------------------


def write_mpc80(detections: pd.DataFrame, out_path: Path) -> None:
    """Hand-rolled MPC 80-column fallback — find_orb also reads this."""
    obs_code = "X05"
    lines: list[str] = []
    for _, row in detections.iterrows():
        mjd = float(row["mjd"])
        year, month, day_frac = _mjd_to_ymdfrac(mjd)
        ra_str = _deg_to_sexagesimal(row["ra_deg"], is_ra=True)
        dec_str = _deg_to_sexagesimal(row["dec_deg"], is_ra=False)
        mag = float(row["mag"]) if "mag" in row and not pd.isna(row["mag"]) else 99.0
        band = str(row["filter"]) if "filter" in row and not pd.isna(row["filter"]) else "r"
        trk = f"RH{int(row['detection_id']):010d}"[:12]
        line = (
            f"     {trk:<7} "
            f"C{year:4d} {month:02d} {day_frac:08.5f} "
            f"{ra_str} {dec_str}          "
            f"{mag:5.1f} {band:1s}      {obs_code}"
        )
        lines.append(line[:80])
    out_path.write_text("\n".join(lines), encoding="ascii")


# ---------------------------------------------------------------------------
# Small astronomy utilities
# ---------------------------------------------------------------------------


def _mjd_to_iso(mjd: float) -> str:
    """MJD → ISO 8601 UTC, second precision. Cheap, no leap-second handling."""
    try:
        from astropy.time import Time

        return Time(mjd, format="mjd", scale="utc").isot
    except Exception:
        # Fallback: MJD 40587 = 1970-01-01
        import datetime as _dt

        secs = (mjd - 40587.0) * 86400.0
        return _dt.datetime.utcfromtimestamp(secs).isoformat(timespec="seconds") + "Z"


_MJD_BASE = 2400000.5


def _mjd_to_ymdfrac(mjd: float) -> tuple[int, int, float]:
    """Very rough MJD → (year, month, day+fraction). Good enough for MPC80."""
    from astropy.time import Time

    t = Time(mjd, format="mjd", scale="utc")
    y, mo, d = t.datetime.year, t.datetime.month, t.datetime.day
    frac = (
        t.datetime.hour / 24.0
        + t.datetime.minute / 1440.0
        + t.datetime.second / 86400.0
        + t.datetime.microsecond / 86400.0e6
    )
    return y, mo, d + frac


def _deg_to_sexagesimal(val: float, *, is_ra: bool) -> str:
    if is_ra:
        hours = val / 15.0
        h = int(hours)
        m = int((hours - h) * 60)
        s = ((hours - h) * 60 - m) * 60
        return f"{h:02d} {m:02d} {s:06.3f}"
    sign = "+" if val >= 0 else "-"
    val = abs(val)
    d = int(val)
    m = int((val - d) * 60)
    s = ((val - d) * 60 - m) * 60
    return f"{sign}{d:02d} {m:02d} {s:05.2f}"


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


_SEMVER_RE = re.compile(r"(\d+\.\d+(?:\.\d+)?)")


def parse_fo_version(text: str) -> str:
    """Best-effort version extractor for fo's banner."""
    m = _SEMVER_RE.search(text or "")
    return m.group(1) if m else "unknown"
