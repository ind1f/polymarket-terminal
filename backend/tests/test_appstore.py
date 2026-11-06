import asyncio
import json

import httpx

from polymarket_terminal.appstore import fetch_chart, merge, parse_page

FEED = {
    "feed": {
        "title": "Top Free Apps",
        "results": [{"id": "1", "name": "First"}, {"id": "2", "name": "Second"}],
    }
}
LOOKUP = {"results": [{"trackId": 1, "averageUserRating": 4.5, "userRatingCount": 900}]}


def page(chart_id: str = "9") -> str:
    def segment(chart, name):
        items = [{"adamId": chart_id, "title": f"{name} app"}]
        return {"chart": chart, "longName": f"Top {name}", "shelves": [{"items": items}]}

    charts = [
        {"ageBandId": "Top Games", "segments": [segment("top-free", "Game")]},
        {
            "ageBandId": "Top Apps",
            "segments": [segment("top-free", "Free"), segment("top-paid", "Paid")],
        },
    ]
    data = json.dumps({"data": [{"data": {"charts": charts}}]})
    return f'<html><script id="serialized-server-data" type="application/json">{data}</script>'


def fetch_with(handler) -> dict:
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_chart(client, "free")

    return asyncio.run(scenario())


def test_merge_keeps_chart_order_and_tolerates_missing_details():
    assert merge(FEED["feed"]["results"], LOOKUP) == [
        {"rank": 1, "id": "1", "name": "First", "values": [4.5, 900]},
        {"rank": 2, "id": "2", "name": "Second", "values": [None, None]},
    ]


def test_fetch_uses_feed_and_lookup():
    def handler(request):
        return httpx.Response(200, json=LOOKUP if "lookup" in str(request.url) else FEED)

    chart = fetch_with(handler)
    assert chart["title"] == "Top Free Apps"
    assert chart["rank_label"] == "Rank"
    assert [row["name"] for row in chart["rows"]] == ["First", "Second"]


def test_parse_page_reads_apps_chart_not_games():
    assert parse_page(page(), "paid") == {
        "title": "Top Paid",
        "results": [{"id": "9", "name": "Paid app"}],
    }


def test_retries_feed_then_falls_back_to_page():
    feed_calls = []

    def handler(request):
        url = str(request.url)
        if "marketingtools" in url:
            feed_calls.append(url)
            raise httpx.ReadTimeout("slow", request=request)
        if "lookup" in url:
            assert request.url.params["id"] == "9"
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, text=page())

    chart = fetch_with(handler)
    assert len(feed_calls) == 2
    assert chart["title"] == "Top Free"
    assert [row["name"] for row in chart["rows"]] == ["Free app"]
