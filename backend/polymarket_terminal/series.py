import asyncio
import json
import logging
import re
import time

import httpx

log = logging.getLogger(__name__)

EVENTS_URL = "https://gamma-api.polymarket.com/events"
SEARCH_URL = "https://gamma-api.polymarket.com/public-search"
SEARCH_PAGES = 5
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DAY_DATE = re.compile(rf"\b({MONTHS}) \d{{1,2}}(?:\s*-\s*(?:(?:{MONTHS}) )?\d{{1,2}})?\b")
MONTH_ONLY = re.compile(rf"\b({MONTHS})\b")
PAGE_SIZE = 100
MAX_PAGES = 10
CACHE_SECONDS = 600
HEADERS = {"User-Agent": "polymarket-terminal"}


def _prices(market: dict) -> list[str]:
    try:
        return json.loads(market.get("outcomePrices") or "[]")
    except ValueError:
        return []


def result(event: dict) -> str | None:
    if not event.get("closed"):
        return None
    markets = event.get("markets") or []
    for market in markets:
        prices = _prices(market)
        if len(markets) > 1 and prices[:1] == ["1"]:
            return market.get("groupItemTitle") or market.get("question")
    active = [market for market in markets if market.get("active") is not False]
    settled = [_prices(market) for market in active]
    if not active or any(sorted(prices) != ["0", "1"] for prices in settled):
        return None
    if len(active) == 1:
        outcomes = json.loads(active[0].get("outcomes") or "[]")
        index = settled[0].index("1")
        return outcomes[index] if index < len(outcomes) else None
    return "None of the listed outcomes"


def undated(title: str) -> str:
    stripped, count = DAY_DATE.subn("", title, count=1)
    if count == 0:
        stripped = MONTH_ONLY.sub("", title, count=1)
    return stripped


def shape(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", undated(title).lower())


def opened(event: dict) -> bool:
    return not event.get("archived") and (event.get("closed") or event.get("active") is not False)


def summarize(event: dict) -> dict:
    return {
        "id": str(event["id"]),
        "title": event.get("title", ""),
        "end_date": event.get("endDate"),
        "closed": bool(event.get("closed")),
        "result": result(event),
    }


async def series_events(client: httpx.AsyncClient, series_id: str) -> list[dict]:
    events: list[dict] = []
    for page in range(MAX_PAGES):
        response = await client.get(
            EVENTS_URL,
            params={
                "series_id": series_id,
                "limit": PAGE_SIZE,
                "offset": page * PAGE_SIZE,
                "order": "endDate",
                "ascending": "false",
            },
            headers=HEADERS,
        )
        response.raise_for_status()
        batch = response.json()
        events.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
    return events


async def search_events(client: httpx.AsyncClient, query: str) -> list[dict]:
    events: list[dict] = []
    for status in ("closed", "active"):
        for page in range(1, SEARCH_PAGES + 1):
            response = await client.get(
                SEARCH_URL,
                params={"q": query, "limit_per_type": 50, "events_status": status, "page": page},
                headers=HEADERS,
            )
            response.raise_for_status()
            found = response.json()
            events.extend(found.get("events") or [])
            if not (found.get("pagination") or {}).get("hasMore"):
                break
    return events


async def fetch_history(client: httpx.AsyncClient, event_id: str) -> dict:
    response = await client.get(f"{EVENTS_URL}/{event_id}", headers=HEADERS)
    response.raise_for_status()
    event = response.json()
    key = shape(event["title"])
    candidates = [event]
    for item in event.get("series") or []:
        candidates += await series_events(client, str(item["id"]))
    query = re.sub(r"[?()]", " ", undated(event["title"]))
    candidates += await search_events(client, " ".join(query.split()))
    unique = {str(item["id"]): item for item in candidates}
    matching = [
        summarize(item)
        for item in unique.values()
        if shape(item.get("title", "")) == key and opened(item)
    ]
    matching.sort(key=lambda item: item["end_date"] or "", reverse=True)
    return {"key": key, "events": matching, "fetched_ms": int(time.time() * 1000)}


class HistoryCache:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self._by_event: dict[str, str] = {}
        self._cached: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def get(self, event_id: str) -> dict:
        async with self._lock:
            key = self._by_event.get(event_id)
            cached = self._cached.get(key) if key else None
            if cached and time.time() - cached["fetched_ms"] / 1000 < CACHE_SECONDS:
                return cached
            try:
                history = await fetch_history(self.client, event_id)
            except (httpx.HTTPError, KeyError, ValueError) as error:
                log.warning("History for event %s failed: %r", event_id, error)
                if cached is None:
                    raise
                return cached
            self._cached[history["key"]] = history
            for item in history["events"]:
                self._by_event[item["id"]] = history["key"]
            self._by_event[event_id] = history["key"]
            return history
