"""Pull the latest ``data/live.sqlite`` from the orphan ``data`` branch.

When the dashboard runs on Streamlit Community Cloud (ADR-0017), the repo
checkout has no ``data/live.sqlite`` — that file lives only on the orphan
``data`` branch which the GitHub Actions pipeline force-pushes after each
run. This module fetches the file lazily via ``raw.githubusercontent.com``
and caches it under ``data/`` so the rest of the dashboard sees a normal
local SQLite.

Behaviour:

- Off by default. Activated by setting the env var
  ``RUBIN_HUNTER_REHYDRATE_URL`` to the raw URL of ``data/live.sqlite``
  on the data branch. On Streamlit Cloud, set this in the app's Secrets
  or env-var configuration. Locally, leaving it unset means the dashboard
  reads ``data/demo.sqlite`` exactly as before.
- Atomic: writes via a tempfile + rename, so a partially-downloaded file
  never replaces a good one.
- Per-session: meant to be called from a ``@st.cache_resource`` boundary
  so it runs once per Streamlit container lifetime (Community Cloud
  recycles every ~24h, which is the right refresh cadence for a 4-hour
  pipeline cron).
- Honest: returns a status dict that the dashboard's data-source chip can
  surface, so the user always knows whether they're seeing a fresh fetch,
  a stale cached copy, or the demo fallback.

The file on the data branch is the *current* DB, not a snapshot — the
pipeline's restore-then-append step on each run preserves history. So
"latest" is always what the dashboard wants.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import requests


@dataclass
class RehydrateResult:
    """Outcome of one rehydrate attempt — exposed in the data-source chip."""

    source: str            # "remote-fresh" | "remote-cached" | "local-only" | "disabled" | "error"
    url: str | None
    dest: Path
    bytes_written: int
    error: str | None
    fetched_at_utc: float  # epoch seconds; 0 if no fetch happened


def _resolve_url() -> str | None:
    """Return the configured remote URL, or ``None`` when rehydrate is off."""
    url = os.environ.get("RUBIN_HUNTER_REHYDRATE_URL", "").strip()
    return url or None


def ensure_live_db(
    dest: Path,
    *,
    url: str | None = None,
    timeout_s: float = 20.0,
) -> RehydrateResult:
    """Make sure ``dest`` holds the latest ``live.sqlite`` from the data branch.

    Resolution:
      1. If the env var ``RUBIN_HUNTER_REHYDRATE_URL`` (or the explicit ``url``
         argument) is empty: do nothing — the caller should fall through to
         the local-disk resolver. ``source = "disabled"``.
      2. Otherwise: GET the URL with ``If-Modified-Since`` derived from
         ``dest``'s mtime, if any. On 304, leave the file alone
         (``source = "remote-cached"``). On 200, atomically replace
         (``source = "remote-fresh"``). On network/HTTP error, leave
         whatever is on disk (``source = "local-only"`` or ``"error"``).

    The caller is expected to wrap this in ``@st.cache_resource`` so it
    runs once per Streamlit container lifetime.
    """
    resolved_url = url if url is not None else _resolve_url()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if resolved_url is None:
        return RehydrateResult(
            source="disabled",
            url=None,
            dest=dest,
            bytes_written=0,
            error=None,
            fetched_at_utc=0.0,
        )

    headers: dict[str, str] = {}
    if dest.exists():
        # HTTP cache-validation against raw.githubusercontent.com. Saves
        # bandwidth + time when the data branch hasn't moved since last fetch.
        ims = time.strftime(
            "%a, %d %b %Y %H:%M:%S GMT", time.gmtime(dest.stat().st_mtime)
        )
        headers["If-Modified-Since"] = ims

    try:
        resp = requests.get(resolved_url, headers=headers, timeout=timeout_s, stream=True)
    except requests.RequestException as exc:
        return RehydrateResult(
            source="error" if not dest.exists() else "local-only",
            url=resolved_url,
            dest=dest,
            bytes_written=0,
            error=f"network: {exc!r}",
            fetched_at_utc=0.0,
        )

    if resp.status_code == 304:
        return RehydrateResult(
            source="remote-cached",
            url=resolved_url,
            dest=dest,
            bytes_written=dest.stat().st_size if dest.exists() else 0,
            error=None,
            fetched_at_utc=0.0,
        )

    if resp.status_code == 404:
        # Data branch hasn't been published yet — first GHA run still pending.
        return RehydrateResult(
            source="local-only" if dest.exists() else "error",
            url=resolved_url,
            dest=dest,
            bytes_written=0,
            error="404: data branch not yet published (waiting for first GHA run)",
            fetched_at_utc=0.0,
        )

    if not resp.ok:
        return RehydrateResult(
            source="error" if not dest.exists() else "local-only",
            url=resolved_url,
            dest=dest,
            bytes_written=0,
            error=f"http {resp.status_code}",
            fetched_at_utc=0.0,
        )

    # Atomic write: tempfile in the same directory, then rename.
    tmp = dest.with_suffix(dest.suffix + ".part")
    written = 0
    try:
        with tmp.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if chunk:
                    fh.write(chunk)
                    written += len(chunk)
        tmp.replace(dest)
    except OSError as exc:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        return RehydrateResult(
            source="error" if not dest.exists() else "local-only",
            url=resolved_url,
            dest=dest,
            bytes_written=0,
            error=f"write: {exc!r}",
            fetched_at_utc=0.0,
        )

    return RehydrateResult(
        source="remote-fresh",
        url=resolved_url,
        dest=dest,
        bytes_written=written,
        error=None,
        fetched_at_utc=time.time(),
    )
