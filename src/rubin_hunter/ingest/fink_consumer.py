"""Fink LSST Kafka consumer.

Per ADR-0003, Fink is one of two live taps for Rubin public alerts (alongside
Lasair-LSST). This module provides a thin wrapper over ``fink-client`` that
subscribes to an LSST topic and pulls decoded alerts for downstream processing.

Per PRD §4 and §6 stage 1, alerts consumed here are intended to be written
verbatim to the raw-alert archive (see :mod:`rubin_hunter.ingest.persistence`
and ADR-0009) before any filtering occurs. This consumer does **not** persist
on its own — that is the caller's responsibility. It also does not mutate the
alert payload.

Offline/demo mode
-----------------
When ``fink-client`` is not importable, or no credentials file is supplied,
the consumer falls back to "offline" mode:

* If local sample AVRO files exist under ``data/samples/*.avro`` they are
  decoded with ``fastavro`` and streamed from ``poll_batch``. This lets the
  dashboard and the rest of the pipeline run end-to-end on a developer box
  without any broker account.
* If no samples are present, ``poll_batch`` returns an empty list and prints
  a one-line advisory.

This is intentional: a fresh clone of the repo should be able to run through
the demo path without any secret configuration. See PRD §4 ("rate and volume
budget") and the milestone M0 bullet in PRD §13.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    # fink-client is optional — it's listed under the ``ingest`` extra.
    # Import failure is expected on a vanilla install; we fall back gracefully.
    from fink_client.consumer import AlertConsumer as _FinkAlertConsumer  # type: ignore
    _FINK_AVAILABLE = True
except Exception:  # pragma: no cover - import guard
    _FinkAlertConsumer = None  # type: ignore
    _FINK_AVAILABLE = False

try:
    import fastavro  # type: ignore
    _FASTAVRO_AVAILABLE = True
except Exception:  # pragma: no cover - import guard
    fastavro = None  # type: ignore
    _FASTAVRO_AVAILABLE = False


_DEFAULT_SAMPLES_DIR = Path(__file__).resolve().parents[3] / "data" / "samples"


@dataclass
class _OfflineState:
    """Bookkeeping for offline-mode replay from local sample AVRO files."""

    sample_files: list[Path] = field(default_factory=list)
    queue: list[dict[str, Any]] = field(default_factory=list)
    exhausted: bool = False


class FinkConsumer:
    """Fink LSST Kafka consumer with an offline/demo fallback.

    Parameters
    ----------
    topic:
        Fink topic name. For Rubin SSO work the current redundant tap is
        ``fink_uniform_sample_lsst`` (PRD §4); a dedicated SSO topic is
        expected in a later Fink release (PRD §13 milestone M10).
    group_id:
        Kafka consumer-group identifier. Use a stable name per host so
        consumption picks up where it left off.
    config_path:
        Path to a YAML file with Fink credentials (``username``,
        ``password``, ``servers``, ...). When ``None`` — or when the file
        does not exist — the consumer starts in offline/demo mode.

    Notes
    -----
    Per ADR-0003, any code that promotes ZTF data onto the science path is
    an invariant violation. This consumer is Rubin/LSST-only; the ZTF
    calibration rail lives in a sibling module.

    Per ADR-0009, alerts pulled here must be persisted verbatim before any
    filtering. This class returns dicts that are either ``fink-client``'s
    own decoded representation (live mode) or ``fastavro``'s decode output
    (offline mode) — both preserve the original AVRO fields.
    """

    def __init__(
        self,
        topic: str,
        group_id: str,
        config_path: Path | None = None,
        offset_reset: str = "latest",
    ) -> None:
        self.topic = topic
        self.group_id = group_id
        self.config_path = Path(config_path) if config_path else None
        # "latest" (default) = only new messages after we subscribe.
        # "earliest" = replay from the Kafka retention window's start —
        # useful on a fresh group_id for a one-shot catch-up run. Honored
        # only on the first offset-resolution for a new consumer group;
        # once Kafka records a committed offset for the group, it reads
        # from there regardless.
        self.offset_reset = offset_reset

        self._live_consumer: Any | None = None
        self._offline: _OfflineState | None = None
        self._mode: str = "uninitialised"

        self._initialise()

    # ------------------------------------------------------------------
    # construction helpers
    # ------------------------------------------------------------------
    def _initialise(self) -> None:
        if self._credentials_available() and _FINK_AVAILABLE:
            try:
                self._live_consumer = self._build_live_consumer()
                self._mode = "live"
                return
            except Exception as exc:  # pragma: no cover - depends on env
                print(
                    f"[fink_consumer] live connect failed ({exc!r}); "
                    "falling back to offline/demo mode."
                )

        # Fall back to offline mode.
        self._offline = self._build_offline_state()
        self._mode = "offline"

        if not _FINK_AVAILABLE:
            print(
                "[fink_consumer] fink-client not installed — running in "
                "offline/demo mode. Install the 'ingest' extra for live access."
            )
        elif not self._credentials_available():
            print(
                "[fink_consumer] no credentials file found — running in "
                "offline/demo mode. Set config_path to a Fink YAML to go live."
            )

        if self._offline is not None and not self._offline.sample_files:
            print(
                "[fink_consumer] no sample AVRO files under data/samples/ — "
                "poll_batch() will return an empty list."
            )

    def _credentials_available(self) -> bool:
        # Resolve a default credentials path if one wasn't provided explicitly.
        # Search order (first hit wins):
        #   1. explicit ``config_path`` constructor arg
        #   2. ``FINK_CLIENT_CONFIG`` env var
        #   3. ``~/.finkclient/credentials.yml`` (fink-client's default)
        if self.config_path is None:
            env_path = os.environ.get("FINK_CLIENT_CONFIG")
            if env_path:
                p = Path(env_path)
                if p.exists():
                    self.config_path = p
                    return True
            default = Path.home() / ".finkclient" / "credentials.yml"
            if default.exists():
                self.config_path = default
                return True
            return False
        return self.config_path.exists()

    def _build_live_consumer(self) -> Any:
        assert _FinkAlertConsumer is not None  # noqa: S101 — guarded above
        # fink-client expects a dict of config values; the YAML file holds
        # Kafka bootstrap servers, SASL credentials, schema registry URL.
        import yaml

        with self.config_path.open("r", encoding="utf-8") as fh:  # type: ignore[union-attr]
            config = yaml.safe_load(fh) or {}
        config["group_id"] = self.group_id
        # auto.offset.reset is passed through to confluent-kafka. Applies
        # only when the (group_id, topic, partition) tuple has no
        # committed offset — e.g. a fresh replay group_id.
        config["auto.offset.reset"] = self.offset_reset
        # fink-client takes a list of topics.
        return _FinkAlertConsumer(topics=[self.topic], config=config)

    def _build_offline_state(self) -> _OfflineState:
        samples_dir = _DEFAULT_SAMPLES_DIR
        samples_dir_env = os.environ.get("RUBIN_HUNTER_SAMPLES_DIR")
        if samples_dir_env:
            samples_dir = Path(samples_dir_env)

        files: list[Path] = []
        if samples_dir.exists():
            files = sorted(Path(p) for p in glob.glob(str(samples_dir / "*.avro")))
        return _OfflineState(sample_files=files)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    @property
    def mode(self) -> str:
        """``"live"`` or ``"offline"`` — useful for logs and dashboards."""
        return self._mode

    def poll_batch(self, max_messages: int, timeout_s: float) -> list[dict[str, Any]]:
        """Return up to ``max_messages`` decoded alert dicts.

        In live mode this calls ``fink-client``'s ``consume`` repeatedly
        until the batch fills or the timeout elapses. In offline mode it
        streams from the pre-loaded sample AVRO files. Either way, the
        returned dicts are the decoded alert payloads — see ADR-0009 for
        the expectation that callers persist the *raw* bytes before
        touching these objects.
        """
        if max_messages <= 0:
            return []

        if self._mode == "live":
            return self._poll_live(max_messages, timeout_s)
        return self._poll_offline(max_messages)

    def _poll_live(self, max_messages: int, timeout_s: float) -> list[dict[str, Any]]:
        assert self._live_consumer is not None  # noqa: S101
        out: list[dict[str, Any]] = []
        remaining_budget = timeout_s
        # fink-client's consume returns (topic, alert, key) triples.
        per_call_timeout = min(timeout_s, 5.0) if timeout_s > 0 else 1.0
        while len(out) < max_messages and remaining_budget > 0:
            try:
                result = self._live_consumer.consume(
                    num_messages=max_messages - len(out),
                    timeout=per_call_timeout,
                )
            except Exception as exc:  # pragma: no cover - depends on env
                print(f"[fink_consumer] live poll error ({exc!r}); returning partial batch.")
                break
            if not result:
                break
            for _topic, alert, _key in result:
                if alert is not None:
                    out.append(alert)
            remaining_budget -= per_call_timeout
        return out

    def _poll_offline(self, max_messages: int) -> list[dict[str, Any]]:
        state = self._offline
        if state is None:
            return []

        # Top up the queue by draining one file at a time until we have
        # enough messages or we run out of sample files.
        while len(state.queue) < max_messages and not state.exhausted:
            if not state.sample_files:
                state.exhausted = True
                break
            path = state.sample_files.pop(0)
            try:
                state.queue.extend(self._decode_avro(path))
            except Exception as exc:
                print(f"[fink_consumer] failed to decode {path}: {exc!r}; skipping.")

        batch, state.queue = state.queue[:max_messages], state.queue[max_messages:]
        return batch

    def _decode_avro(self, path: Path) -> list[dict[str, Any]]:
        if not _FASTAVRO_AVAILABLE:
            print(
                "[fink_consumer] fastavro not installed — cannot decode "
                f"{path}. Install 'fastavro' to enable offline replay."
            )
            return []
        with path.open("rb") as fh:
            reader = fastavro.reader(fh)  # type: ignore[union-attr]
            return list(reader)

    def close(self) -> None:
        """Clean shutdown of the underlying consumer, if any."""
        if self._live_consumer is not None:
            try:
                self._live_consumer.close()
            except Exception as exc:  # pragma: no cover
                print(f"[fink_consumer] close error ignored: {exc!r}")
            finally:
                self._live_consumer = None
        self._offline = None
        self._mode = "closed"

    def __enter__(self) -> "FinkConsumer":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401 - context-manager glue
        self.close()
