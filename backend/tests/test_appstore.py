import asyncio
import json

import httpx

from polymarket_terminal import appstore
from polymarket_terminal.appstore import AppStoreCharts, merge, parse_page

FEED = {
    "feed": {
        "title": "Top Free Apps",
        "results": [{"id": "1", "name": "First"}, {"id": "2", "name": "Second"}],
    }
}
LOOKUP = {"results": [{"trackId": 1, "averageUserRating": 4.5, "userRatingCount": 900}]}


def test_merge_keeps_chart_order_and_tolerates_missing_details():
    assert merge(FEED["feed"]["results"], LOOKUP) == [
        {"rank": 1, "id": "1", "name": "First", "rating": 4.5, "ratings": 900},
        {"rank": 2, "id": "2", "name": "Second", "rating": None, "ratings": None},
    ]


def charts_with(handler) -> AppStoreCharts:
    return AppStoreCharts(httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def respond(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=LOOKUP if "lookup" in str(request.url) else FEED)


def test_second_request_uses_cache():
    calls = []

    def handler(request):
        calls.append(request.url)
        return respond(request)

    async def scenario():
        charts = charts_with(handler)
        first = await charts.get("free")
        second = await charts.get("free")
        assert first is second
        assert first["apps"][0]["ratings"] == 900

    asyncio.run(scenario())
    assert len(calls) == 2


def test_failed_refresh_serves_last_good_chart(monkeypatch):
    failing = {"on": False}

    def handler(request):
        return httpx.Response(500) if failing["on"] else respond(request)

    async def scenario():
        charts = charts_with(handler)
        good = await charts.get("paid")
        failing["on"] = True
        monkeypatch.setattr(appstore, "CACHE_SECONDS", 0)
        assert await charts.get("paid") is good

    asyncio.run(scenario())


def test_failure_without_cache_raises():
    async def scenario():
        charts = charts_with(lambda _: httpx.Response(500))
        try:
            await charts.get("free")
        except httpx.HTTPStatusError:
            return
        raise AssertionError("expected failure")

    asyncio.run(scenario())


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

    chart = asyncio.run(charts_with(handler).get("free"))
    assert len(feed_calls) == 2
    assert chart["title"] == "Top Free"
    assert [app["name"] for app in chart["apps"]] == ["Free app"]


def test_changed_page_format_serves_last_good_chart(monkeypatch):
    broken = {"on": False}

    def handler(request):
        url = str(request.url)
        if broken["on"]:
            if "marketingtools" in url:
                return httpx.Response(500)
            return httpx.Response(200, text="<html>redesigned</html>")
        return respond(request)

    async def scenario():
        charts = charts_with(handler)
        good = await charts.get("free")
        broken["on"] = True
        monkeypatch.setattr(appstore, "CACHE_SECONDS", 0)
        assert await charts.get("free") is good

    asyncio.run(scenario())
