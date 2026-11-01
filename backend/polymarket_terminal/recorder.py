import asyncio
import json
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

log = logging.getLogger(__name__)

DISK_FULL = "Disk nearly full, recording paused"

SCHEMA = pa.schema(
    [
        ("recv_ms", pa.int64()),
        ("event_type", pa.string()),
        ("market", pa.string()),
        ("asset_id", pa.string()),
        ("payload", pa.string()),
    ]
)


class Recorder:
    def __init__(
        self,
        root: Path,
        flush_seconds: float = 60,
        min_free_bytes: int = 5 * 1024**3,
    ) -> None:
        self.root = root
        self.flush_seconds = flush_seconds
        self.min_free_bytes = min_free_bytes
        self.rows_written = 0
        self.rows_dropped = 0
        self.gap_rows = 0
        self.files_written = 0
        self.last_error: str | None = None
        self._rows: list[tuple] = []

    @property
    def buffered(self) -> int:
        return len(self._rows)

    def add(self, recv_ms: int, event: dict) -> None:
        self._rows.append(
            (
                recv_ms,
                event.get("event_type"),
                event.get("market"),
                event.get("asset_id"),
                json.dumps(event, separators=(",", ":")),
            )
        )

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self.flush_seconds)
            await self.flush()

    async def flush(self) -> None:
        if not self._rows:
            return
        rows, self._rows = self._rows, []
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(self.root).free < self.min_free_bytes:
                self.rows_dropped += len(rows)
                self.gap_rows += len(rows)
                self.last_error = DISK_FULL
                log.error("%s, dropped %d rows", DISK_FULL, len(rows))
                return
            if self.gap_rows:
                rows.insert(0, self._gap_row(rows[0][0]))
            await asyncio.to_thread(self._write, rows)
        except (OSError, pa.ArrowException) as error:
            self.last_error = str(error)
            log.error("Recorder flush failed, keeping %d rows: %s", len(rows), error)
            self._rows = rows + self._rows
            return
        self.last_error = None
        self.gap_rows = 0
        self.rows_written += len(rows)
        self.files_written += 1

    def _gap_row(self, recv_ms: int) -> tuple:
        event = {"event_type": "recorder_gap", "dropped_rows": self.gap_rows}
        return (recv_ms, "recorder_gap", None, None, json.dumps(event, separators=(",", ":")))

    def _write(self, rows: list[tuple]) -> None:
        first = rows[0][0]
        started = datetime.fromtimestamp(first / 1000, UTC)
        folder = self.root / f"date={started:%Y-%m-%d}"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{started:%H%M%S}-{first}.parquet"
        temporary = path.with_suffix(".tmp")
        table = pa.table(
            [pa.array(column, type=field.type) for column, field in zip(zip(*rows), SCHEMA)],
            schema=SCHEMA,
        )
        pq.write_table(table, temporary, compression="zstd")
        os.replace(temporary, path)
