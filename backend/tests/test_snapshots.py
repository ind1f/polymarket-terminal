import asyncio
import csv
from datetime import UTC, datetime

from polymarket_terminal.snapshots import capture, due, last_capture, seconds_until_next_hour


class FakeRankings:
    def __init__(self, failing=()):
        self.failing = set(failing)

    async def get(self, chart_id):
        if chart_id in self.failing:
            raise ValueError("source down")
        name = "Free" if chart_id.endswith("free") else "Paid"
        return {
            "rows": [
                {"rank": 1, "id": "11", "name": f"{name} One", "values": [4.5, 900]},
                {"rank": 2, "id": "22", "name": f"{name}, Two", "values": [None, None]},
            ]
        }


NOW = datetime(2026, 11, 4, 18, 0, 3, 123, tzinfo=UTC)


def test_capture_writes_both_charts_with_header(tmp_path):
    path = tmp_path / "rankings" / "appstore.csv"
    assert len(asyncio.run(capture(FakeRankings(), path, NOW))) == 4
    rows = list(csv.DictReader(path.open()))
    assert [(row["chart"], row["rank"], row["name"]) for row in rows] == [
        ("free", "1", "Free One"),
        ("free", "2", "Free, Two"),
        ("paid", "1", "Paid One"),
        ("paid", "2", "Paid, Two"),
    ]
    assert rows[0]["captured_at"] == "2026-11-04T18:00:03+00:00"
    assert rows[1]["rating"] == ""
    assert last_capture(path) == NOW.replace(microsecond=0)


def test_second_capture_appends_without_second_header(tmp_path):
    path = tmp_path / "appstore.csv"
    asyncio.run(capture(FakeRankings(), path, NOW))
    asyncio.run(capture(FakeRankings(), path, NOW.replace(hour=19)))
    lines = path.read_text().splitlines()
    assert lines[0].startswith("captured_at")
    assert sum(line.startswith("captured_at") for line in lines) == 1
    assert len(lines) == 9


def test_one_failing_chart_still_saves_the_other(tmp_path):
    path = tmp_path / "appstore.csv"
    assert len(asyncio.run(capture(FakeRankings(failing={"appstore-paid"}), path, NOW))) == 2


def test_nothing_written_when_every_chart_fails(tmp_path):
    path = tmp_path / "appstore.csv"
    assert asyncio.run(capture(FakeRankings(failing={"appstore-free", "appstore-paid"}), path, NOW)) == []
    assert not path.exists()
    assert last_capture(path) is None


def test_next_hour_wait():
    assert seconds_until_next_hour(datetime(2026, 11, 4, 18, 59, 30, tzinfo=UTC)) == 30
    assert seconds_until_next_hour(datetime(2026, 11, 4, 18, 0, 0, tzinfo=UTC)) == 3600


def test_one_snapshot_per_clock_hour():
    assert due(None, NOW)
    assert not due(datetime(2026, 11, 4, 17, 47, tzinfo=UTC), datetime(2026, 11, 4, 17, 59, tzinfo=UTC))
    assert due(datetime(2026, 11, 4, 17, 47, tzinfo=UTC), datetime(2026, 11, 4, 18, 1, tzinfo=UTC))
    assert due(datetime(2026, 11, 4, 17, 0, 5, tzinfo=UTC), datetime(2026, 11, 4, 18, 0, 5, tzinfo=UTC))
