"""Raw alert archive (per ADR-0009 + PRD §6 stage 1 + PRD §8 N5).

Every alert ingested by the pipeline is persisted **verbatim**. The AVRO
payload is stored as raw bytes; broker cross-match flags (SIMBAD, MPC,
ALeRCE probabilities, etc.) are snapshotted at ingest time into a
sidecar column. Neither is ever mutated later — if a broker updates a
flag we re-query during review and write a *new* annotation, never an
in-place overwrite.

Storage layout
--------------
Parquet files partitioned by calendar UTC ingest date::

    <root>/raw_alerts/YYYY-MM-DD.parquet

One append per alert. Each row has:

* ``alert_id``      — best-effort string id pulled from the alert dict.
* ``ingest_time_utc`` — ingest timestamp (microseconds UTC).
* ``raw_avro_bytes`` — the original AVRO payload. May be ``None`` in
  offline/demo mode where the caller only has a decoded dict; the dict
  is then JSON-encoded into ``raw_json_bytes`` as a best-effort
  replayable representation.
* ``raw_json_bytes`` — JSON encoding of the decoded dict (fallback /
  debug aid).
* ``broker_flags_json`` — JSON snapshot of cross-match flags at ingest.
* ``source_topic``   — where the alert came from (best-effort).

This module intentionally does **no** schema normalisation — downstream
stages read from the detection DB, not from this archive. The archive
exists for reproducibility: PRD §8 N5 requires that "any published
candidate can be regenerated from git commit + local archive".
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


_SCHEMA = pa.schema(
    [
        pa.field("alert_id", pa.string()),
        pa.field("ingest_time_utc", pa.timestamp("us", tz="UTC")),
        pa.field("raw_avro_bytes", pa.binary()),
        pa.field("raw_json_bytes", pa.binary()),
        pa.field("broker_flags_json", pa.string()),
        pa.field("source_topic", pa.string()),
    ]
)


def _coerce_bytes(value: Any) -> bytes | None:
    """Return ``value`` as ``bytes`` if already bytes-like, else ``None``."""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    return None


def _extract_alert_id(alert: dict) -> str:
    """Best-effort alert id extraction across ZTF/LSST schemas."""
    candidates = (
        alert.get("alertId"),
        alert.get("alert_id"),
        alert.get("diaSourceId"),
        alert.get("objectId"),
    )
    for c in candidates:
        if c is not None:
            return str(c)
    return "unknown"


class RawAlertArchive:
    """Append-only Parquet archive, one file per UTC calendar day.

    Per ADR-0009 the bytes stored here must be immutable. The only
    supported mutation of this archive is "add more rows" — deletion or
    edit is a breach of the reproducibility invariant cited in CLAUDE.md.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.alerts_dir = self.root / "raw_alerts"
        self.alerts_dir.mkdir(parents=True, exist_ok=True)

        # One lazily-opened ParquetWriter per UTC day in this process's
        # lifetime. Writers are flushed on close().
        self._writers: dict[date, pq.ParquetWriter] = {}

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _path_for(self, ingest_date: date) -> Path:
        return self.alerts_dir / f"{ingest_date.isoformat()}.parquet"

    def _writer_for(self, ingest_date: date) -> pq.ParquetWriter:
        writer = self._writers.get(ingest_date)
        if writer is not None:
            return writer
        path = self._path_for(ingest_date)
        # pyarrow's ParquetWriter appends iff we open in the same process;
        # across process restarts we accumulate multiple row groups via
        # temp-file concatenation. For simplicity (personal-scale, one
        # writer process per night) we open in "overwrite-or-create" mode
        # per-process and fall back to an append-on-existing path by
        # reading the old file, stitching, and rewriting only when an
        # existing file is found AND this is the first write in this
        # process.
        if path.exists() and writer is None:
            existing = pq.read_table(path, schema=_SCHEMA)
            writer = pq.ParquetWriter(path, _SCHEMA)
            writer.write_table(existing)
        else:
            writer = pq.ParquetWriter(path, _SCHEMA)
        self._writers[ingest_date] = writer
        return writer

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def append(
        self,
        alert: dict,
        broker_flags: dict,
        ingest_time: datetime,
    ) -> None:
        """Append one alert to the archive.

        Parameters
        ----------
        alert:
            The decoded alert dict. If the caller also has the original
            AVRO bytes they should be passed via
            ``alert["_raw_avro_bytes"]`` (the key is stripped before the
            dict is JSON-encoded for storage).
        broker_flags:
            Cross-match / classification flags as observed **at this
            moment**. See ADR-0009: never re-queried in place.
        ingest_time:
            Wall clock at ingest. Timezone-aware; naive datetimes are
            assumed UTC.

        Raises
        ------
        TypeError:
            If ``alert`` is not a dict.
        """
        if not isinstance(alert, dict):
            raise TypeError(f"alert must be a dict, got {type(alert).__name__}")

        if ingest_time.tzinfo is None:
            ingest_time = ingest_time.replace(tzinfo=timezone.utc)
        ingest_time = ingest_time.astimezone(timezone.utc)

        alert_for_json = dict(alert)
        raw_avro = _coerce_bytes(alert_for_json.pop("_raw_avro_bytes", None))
        source_topic = alert_for_json.pop("_source_topic", None)

        try:
            raw_json = json.dumps(alert_for_json, default=str).encode("utf-8")
        except TypeError:
            # Fallback: serialise only the repr when the alert has exotic
            # non-JSON-serialisable fields (e.g. numpy scalars).
            raw_json = repr(alert_for_json).encode("utf-8")

        broker_flags_json = json.dumps(broker_flags, default=str)
        alert_id = _extract_alert_id(alert)

        table = pa.table(
            {
                "alert_id": pa.array([alert_id], type=pa.string()),
                "ingest_time_utc": pa.array([ingest_time], type=pa.timestamp("us", tz="UTC")),
                "raw_avro_bytes": pa.array([raw_avro], type=pa.binary()),
                "raw_json_bytes": pa.array([raw_json], type=pa.binary()),
                "broker_flags_json": pa.array([broker_flags_json], type=pa.string()),
                "source_topic": pa.array(
                    [str(source_topic) if source_topic is not None else None],
                    type=pa.string(),
                ),
            },
            schema=_SCHEMA,
        )

        writer = self._writer_for(ingest_time.date())
        writer.write_table(table)

    def replay(
        self,
        since: datetime,
        until: datetime,
    ) -> Iterator[dict]:
        """Yield archived alerts with ``since <= ingest_time_utc < until``.

        The yielded dicts contain the full row (``alert_id``, times,
        bytes, flags). Callers that need the decoded alert can parse
        ``raw_avro_bytes`` with ``fastavro`` or ``raw_json_bytes`` with
        ``json``.
        """
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        since = since.astimezone(timezone.utc)
        until = until.astimezone(timezone.utc)

        if not self.alerts_dir.exists():
            return

        # Flush any in-flight writers for days we might read back.
        self._flush_writers()

        day = since.date()
        end_day = until.date()
        while day <= end_day:
            path = self._path_for(day)
            if path.exists():
                table = pq.read_table(path)
                times = table.column("ingest_time_utc").to_pylist()
                for idx, t in enumerate(times):
                    # t is a timezone-aware datetime (pyarrow gives us
                    # UTC-tagged datetimes for ``tz="UTC"`` columns).
                    if t is None:
                        continue
                    if t.tzinfo is None:
                        t = t.replace(tzinfo=timezone.utc)
                    if since <= t < until:
                        yield {
                            "alert_id": table.column("alert_id")[idx].as_py(),
                            "ingest_time_utc": t,
                            "raw_avro_bytes": table.column("raw_avro_bytes")[idx].as_py(),
                            "raw_json_bytes": table.column("raw_json_bytes")[idx].as_py(),
                            "broker_flags_json": table.column("broker_flags_json")[idx].as_py(),
                            "source_topic": table.column("source_topic")[idx].as_py(),
                        }
            # advance by one day
            day = date.fromordinal(day.toordinal() + 1)

    def _flush_writers(self) -> None:
        for writer in list(self._writers.values()):
            try:
                writer.close()
            except Exception:
                pass
        self._writers.clear()

    def close(self) -> None:
        """Close any open Parquet writers and flush to disk."""
        self._flush_writers()

    def __enter__(self) -> "RawAlertArchive":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        self.close()
