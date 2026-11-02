import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from polymarket_terminal import appstore, netflix, steam

log = logging.getLogger(__name__)

FETCH_ERRORS = (httpx.HTTPError, AttributeError, KeyError, StopIteration, ValueError)

Fetch = Callable[[httpx.AsyncClient], Awaitable[dict]]


@dataclass(frozen=True)
class Chart:
    fetch: Fetch
    cache_seconds: float


CHARTS = {
    "appstore-free": Chart(lambda client: appstore.fetch_chart(client, "free"), 60),
    "appstore-paid": Chart(lambda client: appstore.fetch_chart(client, "paid"), 60),
    "netflix-global-tv": Chart(lambda client: netflix.fetch_chart(client, "global", "tv"), 1800),
    "netflix-global-films": Chart(
        lambda client: netflix.fetch_chart(client, "global", "films"), 1800
    ),
    "netflix-us-tv": Chart(lambda client: netflix.fetch_chart(client, "us", "tv"), 1800),
    "netflix-us-films": Chart(lambda client: netflix.fetch_chart(client, "us", "films"), 1800),
    "steam-weekly": Chart(steam.fetch_chart, 300),
}


class Rankings:
    def __init__(self, client: httpx.AsyncClient, charts: dict[str, Chart] = CHARTS) -> None:
        self.client = client
        self.charts = charts
        self._cached: dict[str, dict] = {}
        self._locks = {chart_id: asyncio.Lock() for chart_id in charts}

    async def get(self, chart_id: str) -> dict:
        chart = self.charts[chart_id]
        async with self._locks[chart_id]:
            cached = self._cached.get(chart_id)
            if cached and time.time() - cached["fetched_ms"] / 1000 < chart.cache_seconds:
                return cached
            try:
                self._cached[chart_id] = await chart.fetch(self.client) | {"id": chart_id}
            except FETCH_ERRORS as error:
                log.warning("Ranking %s refresh failed: %r", chart_id, error)
                if cached is None:
                    raise
            return self._cached[chart_id]
