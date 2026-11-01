import asyncio
import json
import shutil
from collections import namedtuple

import pyarrow.parquet as pq

from polymarket_terminal.recorder import Recorder

EVENT = {"event_type": "book", "market": "0xabc", "asset_id": "123", "bids": []}


def test_flush_writes_readable_parquet(tmp_path):
    recorder = Recorder(tmp_path, min_free_bytes=0)
    recorder.add(1793555891200, EVENT)
    recorder.add(1793555891300, {"event_type": "feed_disconnected"})
    asyncio.run(recorder.flush())

    files = list(tmp_path.glob("date=*/*.parquet"))
    assert len(files) == 1
    rows = pq.read_table(files[0]).to_pylist()
    assert rows[0]["event_type"] == "book"
    assert rows[0]["asset_id"] == "123"
    assert json.loads(rows[0]["payload"]) == EVENT
    assert rows[1]["market"] is None
    assert recorder.rows_written == 2
    assert recorder.buffered == 0


def test_flush_without_rows_writes_nothing(tmp_path):
    asyncio.run(Recorder(tmp_path).flush())
    assert list(tmp_path.iterdir()) == []


def test_failed_flush_keeps_rows_for_retry(tmp_path):
    blocker = tmp_path / "blocked"
    blocker.write_text("not a folder")
    recorder = Recorder(blocker, min_free_bytes=0)
    recorder.add(1793555891200, EVENT)
    asyncio.run(recorder.flush())
    assert recorder.buffered == 1
    assert recorder.rows_written == 0
    assert recorder.last_error

    recorder.root = tmp_path / "ok"
    recorder.add(1793555891300, EVENT)
    asyncio.run(recorder.flush())
    assert recorder.rows_written == 2
    assert len(list(recorder.root.glob("date=*/*.parquet"))) == 1


def test_low_disk_drops_rows_then_marks_gap_when_space_returns(tmp_path, monkeypatch):
    usage = namedtuple("usage", "free")
    free = {"bytes": 100}
    monkeypatch.setattr(shutil, "disk_usage", lambda _: usage(free["bytes"]))
    recorder = Recorder(tmp_path, min_free_bytes=1000)

    recorder.add(1793555891200, EVENT)
    recorder.add(1793555891300, EVENT)
    asyncio.run(recorder.flush())
    assert recorder.rows_dropped == 2
    assert recorder.buffered == 0
    assert recorder.last_error
    assert list(tmp_path.glob("date=*/*.parquet")) == []

    free["bytes"] = 5000
    recorder.add(1793555891400, EVENT)
    asyncio.run(recorder.flush())
    assert recorder.last_error is None
    rows = pq.read_table(next(tmp_path.glob("date=*/*.parquet"))).to_pylist()
    assert [row["event_type"] for row in rows] == ["recorder_gap", "book"]
    assert json.loads(rows[0]["payload"])["dropped_rows"] == 2
