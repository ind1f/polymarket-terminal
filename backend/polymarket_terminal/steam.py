import json
import logging
import re
import time
from datetime import UTC, datetime, timedelta

import httpx

log = logging.getLogger(__name__)

WEEKLY_URL = "https://api.steampowered.com/IStoreTopSellersService/GetWeeklyTopSellers/v1/"
LIVE_URL = "https://store.steampowered.com/search/results/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15"}
APP_ID = re.compile(r"/apps/(\d+)/")
COLUMNS = [{"label": "Prev", "kind": "rank"}, {"label": "Now", "kind": "rank"}]


def live_ranks(live: dict) -> dict[int, int]:
    ranks: dict[int, int] = {}
    for position, item in enumerate(live.get("items", []), start=1):
        match = APP_ID.search(item.get("logo", ""))
        if match:
            ranks.setdefault(int(match.group(1)), position)
    return ranks


def build(weekly: dict, live: dict[int, int] | None) -> dict:
    response = weekly["response"]
    start = datetime.fromtimestamp(response["start_date"], UTC)
    end = start + timedelta(days=7)
    rows = [
        {
            "rank": item["rank"],
            "name": item["item"]["name"],
            "values": [
                item.get("last_week_rank") or None,
                live.get(item["appid"]) if live is not None else None,
            ],
        }
        for item in response["ranks"]
    ]
    if not rows:
        raise ValueError("Steam weekly chart has no rows")
    return {
        "title": "Steam Weekly Top Sellers · US",
        "period": f"Latest published week {start:%b} {start.day} – {end:%b} {end.day}",
        "rank_label": "Last wk",
        "columns": COLUMNS,
        "rows": rows,
    }


async def fetch_chart(client: httpx.AsyncClient) -> dict:
    request = {
        "country_code": "US",
        "context": {"language": "english", "country_code": "US"},
        "page_count": 100,
        "data_request": {"include_basic_info": True},
    }
    response = await client.get(
        WEEKLY_URL, params={"input_json": json.dumps(request)}, headers=HEADERS
    )
    response.raise_for_status()
    weekly = response.json()
    try:
        response = await client.get(
            LIVE_URL,
            params={"filter": "topsellers", "cc": "us", "l": "english", "json": 1, "count": 100},
            headers=HEADERS,
        )
        response.raise_for_status()
        live = live_ranks(response.json())
    except (httpx.HTTPError, ValueError) as error:
        log.warning("Steam live top sellers failed: %r", error)
        live = None
    return build(weekly, live) | {"fetched_ms": int(time.time() * 1000)}
