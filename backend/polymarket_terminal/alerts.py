import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

CHART_NAMES = {"free": "Top Free Apps", "paid": "Top Paid Apps"}
FULL_CHART = 100


class Telegram:
    def __init__(self, client: httpx.AsyncClient, token: str, chat_id: str) -> None:
        self.client = client
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id

    async def send(self, text: str) -> None:
        response = await self.client.post(self.url, json={"chat_id": self.chat_id, "text": text})
        response.raise_for_status()


def steady_order(app_ids: list[str], old_rank: dict[str, int]) -> list[str]:
    tails: list[int] = []
    tail_index: list[int] = []
    parent = [-1] * len(app_ids)
    for index, app_id in enumerate(app_ids):
        value = old_rank[app_id]
        low, high = 0, len(tails)
        while low < high:
            middle = (low + high) // 2
            if tails[middle] < value:
                low = middle + 1
            else:
                high = middle
        if low > 0:
            parent[index] = tail_index[low - 1]
        if low == len(tails):
            tails.append(value)
            tail_index.append(index)
        else:
            tails[low] = value
            tail_index[low] = index
    result: list[str] = []
    index = tail_index[-1] if tail_index else -1
    while index != -1:
        result.append(app_ids[index])
        index = parent[index]
    return result[::-1]


def chunks(text: str, limit: int = 3900) -> list[str]:
    parts: list[str] = []
    current = ""
    for line in text.split("\n"):
        if current and len(current) + len(line) + 1 > limit:
            parts.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line
    if current:
        parts.append(current)
    return parts


class RankAlerts:
    def __init__(self, telegram: Telegram, app_ids: list[str], state_path: Path, top_n: int = 100) -> None:
        self.telegram = telegram
        self.app_ids = app_ids
        self.state_path = state_path
        self.top_n = top_n
        self.state = self._load()
        self.last_error: str | None = None
        self.sent = 0

    def _load(self) -> dict:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"apps": {}, "top": {}}
        if "apps" not in state:
            return {"apps": state, "top": {}}
        return state

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state), encoding="utf-8")
        os.replace(temporary, self.state_path)

    def _app_changes(self, rows: list[dict], counts: dict[str, int], apps: dict) -> list[str]:
        lines: list[str] = []
        for app_id in self.app_ids:
            matches = {row["chart"]: row for row in rows if str(row.get("app_id")) == app_id}
            previous = apps.get(app_id, {})
            current = dict(previous)
            for chart in counts:
                label = CHART_NAMES.get(chart, chart)
                old = previous.get(chart)
                if chart in matches:
                    rank = int(matches[chart]["rank"])
                    current[chart] = rank
                    name = matches[chart]["name"]
                    if old is None:
                        lines.append(f"{name} entered {label} at #{rank}")
                    elif old != rank:
                        arrow = "▲" if rank < old else "▼"
                        lines.append(f"{name} {arrow} {label}: #{old} → #{rank}")
                elif old is not None and counts[chart] >= FULL_CHART:
                    del current[chart]
                    lines.append(f"App {app_id} left {label} (was #{old})")
            apps[app_id] = current
        return lines

    def _top_changes(self, rows: list[dict], counts: dict[str, int], top: dict) -> list[str]:
        lines: list[str] = []
        for chart in counts:
            ranked = sorted((row for row in rows if row["chart"] == chart), key=lambda row: int(row["rank"]))
            leaders = ranked[: self.top_n]
            if len(leaders) < self.top_n or counts[chart] < self.top_n:
                continue
            stored = top.get(chart)
            top[chart] = [[str(row["app_id"]), row["name"]] for row in leaders]
            if stored is None or len(stored) != self.top_n:
                continue
            old_rank = {entry[0]: index + 1 for index, entry in enumerate(stored)}
            old_names = {entry[0]: entry[1] for entry in stored}
            new_rank = {str(row["app_id"]): int(row["rank"]) for row in leaders}
            names = old_names | {str(row["app_id"]): row["name"] for row in leaders}
            kept = [app_id for app_id in new_rank if app_id in old_rank]
            steady = set(steady_order(kept, old_rank))
            moved = [app_id for app_id in kept if app_id not in steady and old_rank[app_id] != new_rank[app_id]]
            entered = [app_id for app_id in new_rank if app_id not in old_rank]
            dropped = [entry[0] for entry in stored if entry[0] not in new_rank]
            if not (moved or entered or dropped):
                continue
            label = CHART_NAMES.get(chart, chart)
            block = [f"{label} top {self.top_n}:"]
            for app_id in sorted(moved + entered, key=lambda app_id: new_rank[app_id]):
                if app_id in old_rank:
                    arrow = "▲" if new_rank[app_id] < old_rank[app_id] else "▼"
                    block.append(f"{arrow} {names[app_id]}: #{old_rank[app_id]} → #{new_rank[app_id]}")
                else:
                    block.append(f"New: {names[app_id]} at #{new_rank[app_id]}")
            for app_id in sorted(dropped, key=lambda app_id: old_rank[app_id]):
                block.append(f"Out: {names[app_id]} (was #{old_rank[app_id]})")
            lines.append("\n".join(block))
        return lines

    async def check(self, rows: list[dict], counts: dict[str, int]) -> None:
        apps = json.loads(json.dumps(self.state["apps"]))
        top = json.loads(json.dumps(self.state["top"]))
        lines = self._app_changes(rows, counts, apps) + self._top_changes(rows, counts, top)
        if lines:
            stamp = rows[0]["captured_at"][11:16] if rows else ""
            try:
                for part in chunks("\n\n".join(lines) + f"\n\n(App Store check {stamp} UTC)"):
                    await self.telegram.send(part)
                self.sent += 1
                self.last_error = None
            except httpx.HTTPError as error:
                self.last_error = repr(error)
                log.error("Telegram alert failed, will retry next check: %r", error)
                return
        self.state = {"apps": apps, "top": top}
        await asyncio.to_thread(self._save)


class AlertLoop:
    def __init__(
        self,
        alerts: RankAlerts,
        collect,
        interval_seconds: float = 300,
        tick_seconds: float = 30,
    ) -> None:
        self.alerts = alerts
        self.collect = collect
        self.interval_seconds = interval_seconds
        self.tick_seconds = tick_seconds
        self.last_check: datetime | None = None
        self._last_attempt: datetime | None = None

    async def run(self) -> None:
        while True:
            now = datetime.now(UTC)
            elapsed = (now - self._last_attempt).total_seconds() if self._last_attempt else None
            if elapsed is None or elapsed >= self.interval_seconds:
                self._last_attempt = now
                rows, counts = await self.collect(now)
                if counts:
                    try:
                        await self.alerts.check(rows, counts)
                        self.last_check = now
                    except OSError as error:
                        log.error("Alert check failed: %s", error)
            await asyncio.sleep(min(self.tick_seconds, self.interval_seconds / 6))
