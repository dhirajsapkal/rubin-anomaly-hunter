"""All-sky detection map rendered as an inline SVG string.

Mollweide projection of tonight's detections, colour-coded by band, with
flagged detections circled in amber. Galactic-plane and ecliptic overlays
are drawn as dashed grey curves. Transparent background so the surrounding
`.sky-map` wrapper colours show through. Palette and typography match the
Mission-Control Modern theme (see `dashboard/static/theme.css`).

Not on the science path — purely presentational.
"""

from __future__ import annotations

import io

import numpy as np

try:  # matplotlib is in pyproject.toml but guard anyway
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _HAS_MPL = True
except Exception:
    _HAS_MPL = False


# Band -> colour mapping (matches light-curve in mockimg.py where it overlaps)
_BAND_COLOR = {
    "u": "#A5B4FC",
    "g": "#A5B4FC",
    "r": "#FDBA74",
    "i": "#F87171",
    "z": "#7DD3FC",
    "y": "#FFB020",
}
_DEFAULT_DOT_COLOR = "#6D7595"
_FLAG_RING_COLOR = "#FFB020"


def _empty_svg(message: str, width: float, height: float) -> str:
    w, h = int(width * 72), int(height * 72)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}">'
        f'<text x="{w//2}" y="{h//2}" text-anchor="middle" '
        f'dominant-baseline="middle" font-family="IBM Plex Mono, monospace" '
        f'font-style="italic" font-size="12" fill="#5B6275">{message}</text>'
        f'</svg>'
    )


def _wrap_lon_rad(lon_deg: np.ndarray) -> np.ndarray:
    """Wrap longitude to [-pi, +pi] radians (mollweide expects -pi..+pi)."""
    x = np.asarray(lon_deg, dtype=float)
    # RA 0..360 -> -180..180 so Mollweide centres on 0h
    x = ((x + 180.0) % 360.0) - 180.0
    return np.deg2rad(x)


def _galactic_plane_equatorial(n: int = 400) -> tuple[np.ndarray, np.ndarray]:
    """Approximate the galactic plane (b=0) in equatorial RA/Dec degrees.

    Rotation matrix from galactic -> equatorial (J2000), applied to a ring
    at galactic latitude b=0. Standard angles from the IAU.
    """
    l = np.linspace(0.0, 2 * np.pi, n)
    b = np.zeros_like(l)
    # Galactic cartesian
    xg = np.cos(b) * np.cos(l)
    yg = np.cos(b) * np.sin(l)
    zg = np.sin(b)
    # Galactic north pole in equatorial: RA=192.8595°, Dec=+27.1283°
    # Galactic centre longitude: theta0 = 122.9320° (used in standard matrix)
    a_ngp = np.deg2rad(192.8595)
    d_ngp = np.deg2rad(27.1283)
    theta0 = np.deg2rad(122.9320)
    # Standard galactic->equatorial rotation matrix
    sa, ca = np.sin(a_ngp), np.cos(a_ngp)
    sd, cd = np.sin(d_ngp), np.cos(d_ngp)
    st, ct = np.sin(theta0), np.cos(theta0)
    R = np.array([
        [-sa * ct - ca * sd * st,  ca * ct - sa * sd * st,  cd * st],
        [ sa * st - ca * sd * ct, -ca * st - sa * sd * ct,  cd * ct],
        [ ca * cd,                  sa * cd,                 sd     ],
    ])
    # The rows above map galactic->equatorial (x_eq = R . x_gal)
    eq = R @ np.vstack([xg, yg, zg])
    xe, ye, ze = eq[0], eq[1], eq[2]
    ra = np.rad2deg(np.arctan2(ye, xe)) % 360.0
    dec = np.rad2deg(np.arcsin(np.clip(ze, -1, 1)))
    return ra, dec


def _ecliptic_equatorial(n: int = 400) -> tuple[np.ndarray, np.ndarray]:
    """Ecliptic (b=0) in equatorial RA/Dec degrees. Obliquity = 23.4393°."""
    lam = np.linspace(0.0, 2 * np.pi, n)
    eps = np.deg2rad(23.4393)
    # Ecliptic cartesian (beta=0) -> equatorial
    xe = np.cos(lam)
    ye = np.sin(lam) * np.cos(eps)
    ze = np.sin(lam) * np.sin(eps)
    ra = np.rad2deg(np.arctan2(ye, xe)) % 360.0
    dec = np.rad2deg(np.arcsin(np.clip(ze, -1, 1)))
    return ra, dec


def _plot_wrapped_curve(ax, ra_deg: np.ndarray, dec_deg: np.ndarray, **kw) -> None:
    """Plot a curve in mollweide coords, breaking segments at the RA wrap.

    A naive plot of points that jump from +180 to -180 would draw a long
    horizontal line across the map; detect big jumps and split.
    """
    lon = _wrap_lon_rad(ra_deg)
    lat = np.deg2rad(dec_deg)
    # Break at discontinuities > ~pi in longitude
    d = np.abs(np.diff(lon))
    splits = np.where(d > np.pi * 0.9)[0]
    start = 0
    for s in splits:
        ax.plot(lon[start:s + 1], lat[start:s + 1], **kw)
        start = s + 1
    ax.plot(lon[start:], lat[start:], **kw)


def all_sky_svg(
    detections: list[dict],
    width: float = 5.6,
    height: float = 3.2,
    title: str | None = None,
) -> str:
    """Render tonight's detections on a Mollweide all-sky projection.

    Parameters
    ----------
    detections:
        Iterable of dicts with keys ``ra_deg``, ``dec_deg``, ``band``,
        ``flagged``. Extra keys are ignored.
    width, height:
        Matplotlib figure size in inches.
    title:
        Optional title rendered in IBM Plex Mono above the map.

    Returns
    -------
    SVG string (transparent background). Empty-state svg if ``detections``
    is empty.
    """
    if not _HAS_MPL:
        return _empty_svg("matplotlib missing", width, height)
    if not detections:
        return _empty_svg("no detections tonight.", width, height)

    fig = plt.figure(figsize=(width, height))
    fig.patch.set_alpha(0.0)
    ax = fig.add_subplot(111, projection="mollweide")
    ax.set_facecolor("none")

    # Strip every decoration, then re-add a minimal grid.
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(True, color="#252C3C", linewidth=0.5, alpha=0.6)
    # Mollweide grid spacing — matplotlib handles major gridlines via locators.
    try:
        from matplotlib.ticker import MultipleLocator
        ax.xaxis.set_major_locator(MultipleLocator(np.deg2rad(30)))
        ax.yaxis.set_major_locator(MultipleLocator(np.deg2rad(30)))
    except Exception:
        pass

    # Tick labels — tiny, Plex Mono, tertiary colour.
    ax.tick_params(colors="#5B6275", labelsize=7)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_fontfamily("monospace")
    # Hide longitude tick labels — they're noisy on a world-sky view.
    ax.set_xticklabels([])

    # Galactic plane (dashed, cool-grey)
    gra, gdec = _galactic_plane_equatorial()
    _plot_wrapped_curve(
        ax, gra, gdec,
        color="#384053", linestyle=(0, (4, 3)), linewidth=0.9, alpha=0.85,
        zorder=2,
    )
    # Ecliptic (dashed, amber-muted)
    era, edec = _ecliptic_equatorial()
    _plot_wrapped_curve(
        ax, era, edec,
        color="#6B5015", linestyle=(0, (2, 3)), linewidth=0.9, alpha=0.85,
        zorder=2,
    )

    # Detections — group by band so marker colours are vectorised.
    by_band: dict[str, list[tuple[float, float, bool]]] = {}
    for d in detections:
        try:
            ra = float(d["ra_deg"])
            dec = float(d["dec_deg"])
        except (KeyError, TypeError, ValueError):
            continue
        band = (d.get("band") or "r").lower()
        flagged = bool(d.get("flagged"))
        by_band.setdefault(band, []).append((ra, dec, flagged))

    flagged_xy: list[tuple[float, float]] = []
    for band, pts in sorted(by_band.items()):
        xs = _wrap_lon_rad(np.array([p[0] for p in pts]))
        ys = np.deg2rad(np.array([p[1] for p in pts]))
        color = _BAND_COLOR.get(band, _DEFAULT_DOT_COLOR)
        ax.scatter(
            xs, ys, s=6.5, c=color, alpha=0.85,
            linewidths=0, zorder=4,
        )
        for p in pts:
            if p[2]:
                flagged_xy.append((p[0], p[1]))

    # Flagged overlay — amber ring, ~2.5x larger than the dots.
    if flagged_xy:
        fx = _wrap_lon_rad(np.array([p[0] for p in flagged_xy]))
        fy = np.deg2rad(np.array([p[1] for p in flagged_xy]))
        ax.scatter(
            fx, fy, s=38, facecolors="none",
            edgecolors=_FLAG_RING_COLOR, linewidths=1.2,
            alpha=0.95, zorder=6,
        )

    if title:
        ax.set_title(
            title,
            color="#5B6275",
            fontsize=9,
            family="monospace",
            pad=6,
            loc="left",
        )

    fig.tight_layout(pad=0.3)
    buf = io.StringIO()
    fig.savefig(
        buf, format="svg", transparent=True,
        bbox_inches="tight", pad_inches=0.12,
    )
    plt.close(fig)
    return buf.getvalue()
