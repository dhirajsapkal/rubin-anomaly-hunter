"""Deterministic synthetic imagery for the dashboard demo.

The demo SQLite does not contain real FITS cutouts or light-curve data — those
only arrive when the live alert stream is connected. To let the user evaluate
the Candidate Detail page before plumbing is finished, we synthesize:

  - 63x63 'science', 'template', and 'difference' cutouts (procedural starfield
    with a Gaussian point source in each, correctly noise-matched)
  - light-curve matplotlib SVGs
  - top-down ecliptic orbit matplotlib SVGs

Every synthetic asset is seeded deterministically from the entry_id so the
images are stable across reloads. A faint 'synthetic — demo mode' watermark is
composited onto cutouts so the user never mistakes them for real data.

None of these functions are on the science path. See PRD §11, ADR-0005.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass

import numpy as np

try:  # matplotlib is in pyproject.toml but guard anyway
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _HAS_MPL = True
except Exception:
    _HAS_MPL = False

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


# -------- Cutouts ---------------------------------------------------------

_STAR_COUNT = 18
_CUTOUT_SIZE = 63
_DISPLAY_SIZE = 120


def _rng(entry_id: int, detection_idx: int, stamp: str) -> np.random.Generator:
    salt = {"science": 101, "template": 211, "difference": 307}.get(stamp, 1)
    return np.random.default_rng(entry_id * 100003 + detection_idx * 131 + salt)


def _starfield(rng: np.random.Generator, size: int = _CUTOUT_SIZE) -> np.ndarray:
    base = rng.normal(loc=0.12, scale=0.035, size=(size, size)).astype(np.float32)
    base = np.clip(base, 0, 1)
    # Background stars
    for _ in range(_STAR_COUNT):
        cx, cy = rng.integers(0, size), rng.integers(0, size)
        amp = rng.uniform(0.1, 0.5)
        xv = np.arange(size) - cx
        yv = np.arange(size) - cy
        sigma = rng.uniform(0.9, 1.6)
        g = np.exp(-(xv[None, :] ** 2 + yv[:, None] ** 2) / (2 * sigma ** 2))
        base += amp * g.astype(np.float32)
    return np.clip(base, 0, 1)


def _render_cutout(
    entry_id: int,
    detection_idx: int,
    stamp: str,
    source_flux: float = 0.7,
) -> "Image.Image":
    if not _HAS_PIL:
        raise RuntimeError("Pillow not installed — cannot render cutouts")
    rng = _rng(entry_id, detection_idx, stamp)
    size = _CUTOUT_SIZE
    arr = _starfield(rng, size)
    cx = size // 2 + rng.integers(-2, 3)
    cy = size // 2 + rng.integers(-2, 3)
    xv = np.arange(size) - cx
    yv = np.arange(size) - cy
    if stamp == "science":
        amp = source_flux
    elif stamp == "template":
        amp = 0.0
    else:  # difference
        # Clean up background, keep a centered residual with Gaussian PSF
        arr = np.clip(rng.normal(0, 0.02, (size, size)).astype(np.float32), -0.5, 0.5) + 0.12
        amp = source_flux * 0.85
    sigma = 1.35
    g = np.exp(-(xv[None, :] ** 2 + yv[:, None] ** 2) / (2 * sigma ** 2))
    arr = arr + amp * g.astype(np.float32)
    # Normalize to 0..255 uint8 with ZScale-like tonal mapping
    lo, hi = np.percentile(arr, [2, 99.3])
    arr = (arr - lo) / max(hi - lo, 1e-6)
    arr = np.clip(arr, 0, 1)
    img8 = (arr * 255).astype(np.uint8)

    # 3-channel with a subtle warm tint on science, cool on template, neutral on diff
    if stamp == "science":
        tint = np.array([1.03, 0.98, 0.88], dtype=np.float32)
    elif stamp == "template":
        tint = np.array([0.88, 0.95, 1.05], dtype=np.float32)
    else:
        tint = np.array([1.0, 1.0, 1.0], dtype=np.float32)
    rgb = np.stack([img8, img8, img8], axis=-1).astype(np.float32)
    rgb *= tint[None, None, :]
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)

    img = Image.fromarray(rgb, mode="RGB").resize(
        (_DISPLAY_SIZE, _DISPLAY_SIZE), Image.NEAREST
    )
    # Watermark — subtle, not centered over the source
    draw = ImageDraw.Draw(img)
    wm = "demo"
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((6, _DISPLAY_SIZE - 14), wm, fill=(160, 160, 160), font=font)
    return img


def cutout_b64(entry_id: int, detection_idx: int, stamp: str) -> str:
    """Return a data:image/png;base64,... URI for embedding in HTML."""
    if not _HAS_PIL:
        return ""
    img = _render_cutout(entry_id, detection_idx, stamp)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# -------- Light curve -----------------------------------------------------

def light_curve_svg(
    entry_id: int,
    detections: list[dict],
    width: float = 6.8,
    height: float = 2.2,
) -> str:
    """Render a multi-band light curve to inline SVG string."""
    if not _HAS_MPL or not detections:
        return _empty_svg("no light-curve data", width, height)
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor("#F2E8D5")
    ax.set_facecolor("#F2E8D5")
    for spine in ax.spines.values():
        spine.set_color("#D4C9B0")
    ax.tick_params(colors="#555770", labelsize=8)
    ax.set_xlabel("MJD", color="#555770", fontsize=9)
    ax.set_ylabel("PSF flux (nJy)", color="#555770", fontsize=9)

    band_color = {
        "u": "#6B8C37",
        "g": "#6B8C37",
        "r": "#E8A87C",
        "i": "#C88BD0",
        "z": "#7BA9D9",
        "y": "#D9B06C",
    }
    band_marker = {"u": "^", "g": "o", "r": "o", "i": "s", "z": "D", "y": "v"}

    by_band: dict[str, list[tuple[float, float, float]]] = {}
    for d in detections:
        by_band.setdefault(d.get("band") or "r", []).append(
            (float(d["mjd"]), float(d.get("psf_flux") or 0), float(d.get("psf_flux_err") or 0))
        )

    for band, pts in sorted(by_band.items()):
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        es = [p[2] for p in pts]
        color = band_color.get(band, "#6D7595")
        marker = band_marker.get(band, "o")
        ax.errorbar(
            xs, ys, yerr=es, fmt=marker, color=color, ecolor=color, capsize=0,
            markersize=5, markerfacecolor=color, alpha=0.9, label=band,
        )

    ax.legend(
        frameon=False, fontsize=8, loc="upper right",
        labelcolor="#555770", handlelength=0.8,
    )
    fig.tight_layout(pad=0.5)

    buf = io.StringIO()
    fig.savefig(buf, format="svg", transparent=False, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return buf.getvalue()


# -------- Orbit plot ------------------------------------------------------

_PLANET_SEMIMAJOR_AU = {
    "Mercury": 0.387, "Venus": 0.723, "Earth": 1.0,
    "Mars": 1.524, "Jupiter": 5.203, "Saturn": 9.537,
}


@dataclass
class OrbitParams:
    a_au: float
    e: float
    incl_deg: float
    perihelion_au: float | None = None
    aphelion_au: float | None = None
    category: str = "dark_comet"


def orbit_svg(p: OrbitParams, width: float = 4.6, height: float = 4.6) -> str:
    if not _HAS_MPL:
        return _empty_svg("matplotlib missing", width, height)
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor("#F2E8D5")
    ax.set_facecolor("#F2E8D5")
    ax.set_aspect("equal", adjustable="box")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors="#555770", labelsize=8)

    # Planet rings (circular top-down approximation)
    for name, ra in _PLANET_SEMIMAJOR_AU.items():
        theta = np.linspace(0, 2 * np.pi, 240)
        ax.plot(
            ra * np.cos(theta), ra * np.sin(theta),
            color="#D4C9B0", linewidth=0.8, zorder=1,
        )
        ax.plot(ra, 0, marker="o", markersize=3, color="#555770", zorder=2)
        ax.text(
            ra + 0.08, 0.05, name, fontsize=8, color="#555770",
            style="italic", alpha=0.8,
        )
    # Sun
    ax.plot(0, 0, marker="o", markersize=5, color="#D9B06C", zorder=3)

    # Fit orbit: handle bound vs. hyperbolic
    color_kind = "#C88BD0" if p.category == "dark_comet" else "#E8A87C"
    if p.e < 1.0 and p.a_au > 0:
        # Ellipse
        a, e = p.a_au, p.e
        b = a * np.sqrt(max(1 - e * e, 0))
        theta = np.linspace(0, 2 * np.pi, 400)
        x = a * np.cos(theta) - a * e
        y = b * np.sin(theta)
        ax.plot(x, y, color=color_kind, linewidth=1.8, zorder=4)
    else:
        # Hyperbolic branch (ISO-like); p = a * (1 - e^2), for e>1 use p = q(1+e)
        q = p.perihelion_au or max(abs(p.a_au) * abs(1 - p.e), 0.1)
        e = max(p.e, 1.0 + 1e-3)
        th = np.linspace(-np.pi * 0.6, np.pi * 0.6, 400)
        r = q * (1 + e) / (1 + e * np.cos(th))
        x = r * np.cos(th)
        y = r * np.sin(th)
        ax.plot(x, y, color=color_kind, linewidth=1.8, zorder=4)

    # Current position marker (phosphor)
    if p.e < 1:
        ax.plot(
            (p.perihelion_au or 0.5), 0, marker="o", markersize=7,
            markerfacecolor="#B9F15D", markeredgecolor="#1A1A2E",
            markeredgewidth=0.8, zorder=6,
        )
    else:
        ax.plot(
            p.perihelion_au or 1.3, 0, marker="o", markersize=7,
            markerfacecolor="#B9F15D", markeredgecolor="#1A1A2E",
            markeredgewidth=0.8, zorder=6,
        )

    # Frame extent
    lim = max(6.0, (p.aphelion_au or abs(p.a_au) * (1 + p.e)) * 1.15, 6.5)
    lim = min(lim, 15.0)
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_xticks([])
    ax.set_yticks([])

    # Caption
    peri = f"{p.perihelion_au:.2f}" if p.perihelion_au else "—"
    ap = f"{p.aphelion_au:.2f}" if (p.aphelion_au and p.e < 1) else "∞"
    ax.text(
        -lim * 0.95, -lim * 0.95,
        f"a={p.a_au:+.2f} AU  e={p.e:.3f}  i={p.incl_deg:.1f}°  q={peri}  Q={ap}",
        fontsize=9, family="monospace", color="#1A1A2E",
    )

    fig.tight_layout(pad=0.2)
    buf = io.StringIO()
    fig.savefig(buf, format="svg", transparent=False, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return buf.getvalue()


# -------- Pipeline health sparkline ---------------------------------------

def sparkline_svg(
    values: list[float],
    width: float = 4.8,
    height: float = 0.9,
    threshold: float | None = None,
    color: str = "#B9F15D",
) -> str:
    if not _HAS_MPL or not values:
        return _empty_svg("—", width, height)
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor("#131A2E")
    ax.set_facecolor("#131A2E")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])
    xs = np.arange(len(values))
    ax.plot(xs, values, color=color, linewidth=1.4)
    ax.scatter(xs, values, s=6, color=color, zorder=3)
    if threshold is not None:
        ax.axhline(threshold, color="#6D7595", linestyle="--", linewidth=0.8)
    fig.tight_layout(pad=0.1)
    buf = io.StringIO()
    fig.savefig(buf, format="svg", transparent=False, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    return buf.getvalue()


def _empty_svg(message: str, width: float, height: float) -> str:
    w, h = int(width * 72), int(height * 72)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<rect width="100%" height="100%" fill="#F2E8D5"/>'
        f'<text x="{w//2}" y="{h//2}" text-anchor="middle" dominant-baseline="middle" '
        f'font-family="JetBrains Mono, monospace" font-size="12" fill="#6D7595">{message}</text>'
        f'</svg>'
    )
