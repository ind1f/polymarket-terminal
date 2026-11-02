import json
import logging
import re
import time

import httpx

log = logging.getLogger(__name__)

FEED_URL = "https://rss.marketingtools.apple.com/api/v2/us/apps/top-{chart}/100/apps.json"
PAGE_URL = "https://apps.apple.com/us/iphone/charts"
LOOKUP_URL = "https://itunes.apple.com/lookup"
FEED_TIMEOUT_SECONDS = 6
FEED_ATTEMPTS = 2
PAGE_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15"}
PAGE_DATA = re.compile(r'<script[^>]*id="serialized-server-data"[^>]*>(.*?)</script>', re.S)
COLUMNS = [{"label": "Rating", "kind": "rating"}, {"label": "Ratings", "kind": "count"}]


def parse_page(html: str, chart: str) -> dict:
    data = json.loads(PAGE_DATA.search(html).group(1))
    charts = data["data"][0]["data"]["charts"]
    apps_chart = next(item for item in charts if item["ageBandId"] == "Top Apps")
    segment = next(item for item in apps_chart["segments"] if item["chart"] == f"top-{chart}")
    items = [item for shelf in segment["shelves"] for item in shelf["items"]]
    return {
        "title": segment["longName"],
        "results": [{"id": item["adamId"], "name": item["title"]} for item in items],
    }


def merge(results: list[dict], lookup: dict) -> list[dict]:
    details = {str(item["trackId"]): item for item in lookup.get("results", [])}
    rows = []
    for rank, app in enumerate(results, start=1):
        detail = details.get(app["id"], {})
        rows.append(
            {
                "rank": rank,
                "name": app["name"],
                "values": [detail.get("averageUserRating"), detail.get("userRatingCount")],
            }
        )
    return rows


async def fetch_chart(client: httpx.AsyncClient, chart: str) -> dict:
    ranking = await _ranking(client, chart)
    ids = ",".join(app["id"] for app in ranking["results"])
    response = await client.get(LOOKUP_URL, params={"country": "us", "id": ids})
    response.raise_for_status()
    return {
        "title": ranking["title"],
        "period": None,
        "rank_label": "Rank",
        "columns": COLUMNS,
        "rows": merge(ranking["results"], response.json()),
        "fetched_ms": int(time.time() * 1000),
    }


async def _ranking(client: httpx.AsyncClient, chart: str) -> dict:
    for _ in range(FEED_ATTEMPTS):
        try:
            response = await client.get(FEED_URL.format(chart=chart), timeout=FEED_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()["feed"]
        except (httpx.HTTPError, KeyError, ValueError) as error:
            log.info("App Store %s feed failed: %r", chart, error)
    response = await client.get(PAGE_URL, headers=PAGE_HEADERS, follow_redirects=True)
    response.raise_for_status()
    return parse_page(response.text, chart)
