import asyncio
import csv
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from polymarket_terminal.rankings import FETCH_ERRORS, Rankings

log = logging.getLogger(__name__)

TICK_SECONDS = 30
FIELDS = ["captured_at", "chart", "rank", "app_id", "name", "rating", "ratings"]
CHARTS = {"free": "appstore-free", "paid": "appstore-paid"}


def last_capture(path: Path) -> datetime | None:
    if not path.exists():
        return None
    with path.open("rb") as file:
        file.seek(0, os.SEEK_END)
        file.seek(max(0, file.tell() - 4096))
        lines = file.read().decode("utf-8", errors="replace").strip().splitlines()
    for line in reversed(lines):
        stamp = line.split(",", 1)[0]
        try:
            return datetime.fromisoformat(stamp)
        except ValueError:
            continue
    return None


def hour_of(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def due(last: datetime | None, now: datetime) -> bool:
    return last is None or hour_of(now) > hour_of(last)


def seconds_until_next_hour(now: datetime) -> float:
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return (next_hour - now).total_seconds()


def _append(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        if new:
            writer.writeheader()
        writer.writerows(rows)


async def collect(rankings: Rankings, now: datetime) -> tuple[list[dict], dict[str, int]]:
    stamp = now.replace(microsecond=0).isoformat()
    rows: list[dict] = []
    counts: dict[str, int] = {}
    for chart, chart_id in CHARTS.items():
        try:
            data = await rankings.get(chart_id)
        except FETCH_ERRORS as error:
            log.warning("App Store %s chart unavailable: %r", chart, error)
            continue
        counts[chart] = len(data["rows"])
        for row in data["rows"]:
            rating, ratings = (row["values"] + [None, None])[:2]
            rows.append(
                {
                    "captured_at": stamp,
                    "chart": chart,
                    "rank": row["rank"],
                    "app_id": row.get("id"),
                    "name": row["name"],
                    "rating": rating,
                    "ratings": ratings,
                }
            )
    return rows, counts


async def capture(rankings: Rankings, path: Path, now: datetime) -> list[dict]:
    rows, _ = await collect(rankings, now)
    if rows:
        await asyncio.to_thread(_append, path, rows)
    return rows


class Snapshotter:
    def __init__(self, rankings: Rankings, path: Path) -> None:
        self.rankings = rankings
        self.path = path
        self.last: datetime | None = None
        self.last_rows = 0
        self.last_error: str | None = None

    async def run(self) -> None:
        self.last = await asyncio.to_thread(last_capture, self.path)
        while True:
            now = datetime.now(UTC)
            if due(self.last, now):
                try:
                    rows = await capture(self.rankings, self.path, now)
                    self.last_rows = len(rows)
                    if rows:
                        self.last = now
                    self.last_error = None
                except OSError as error:
                    self.last_error = str(error)
                    log.error("App Store snapshot failed: %s", error)
            await asyncio.sleep(min(TICK_SECONDS, seconds_until_next_hour(datetime.now(UTC)) + 5))
