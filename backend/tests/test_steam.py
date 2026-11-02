import asyncio

import httpx

from polymarket_terminal.steam import build, fetch_chart, live_ranks

WEEKLY = {
    "response": {
        "start_date": 1792454400,
        "ranks": [
            {"rank": 1, "appid": 10, "item": {"name": "Game A®"}, "last_week_rank": 1},
            {"rank": 2, "appid": 20, "item": {"name": "Game B"}, "last_week_rank": 0},
        ],
    }
}
LIVE = {
    "items": [
        {"name": "Hardware", "logo": "https://x/steam/apps/99/a.jpg"},
        {"name": "Game B", "logo": "https://x/steam/apps/20/b.jpg"},
        {"name": "Game B again", "logo": "https://x/steam/apps/20/c.jpg"},
    ]
}


def test_live_ranks_use_app_ids_and_first_position():
    assert live_ranks(LIVE) == {99: 1, 20: 2}


def test_build_joins_previous_and_live_ranks():
    chart = build(WEEKLY, live_ranks(LIVE))
    assert chart["period"] == "Latest published week Oct 20 – Oct 27"
    assert chart["rows"] == [
        {"rank": 1, "name": "Game A®", "values": [1, None]},
        {"rank": 2, "name": "Game B", "values": [None, 2]},
    ]


def test_live_failure_still_returns_weekly_chart():
    def handler(request):
        if "search" in str(request.url):
            return httpx.Response(503)
        return httpx.Response(200, json=WEEKLY)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_chart(client)

    chart = asyncio.run(scenario())
    assert [row["values"] for row in chart["rows"]] == [[1, None], [None, None]]
