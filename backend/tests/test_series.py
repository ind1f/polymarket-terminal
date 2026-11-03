import asyncio
import json

import httpx

from polymarket_terminal.series import fetch_history, result, shape


def market(title, prices, active=True, outcomes=("Yes", "No")):
    return {
        "groupItemTitle": title,
        "outcomePrices": json.dumps(prices),
        "outcomes": json.dumps(list(outcomes)),
        "active": active,
    }


def test_multi_outcome_winner_skips_placeholders():
    event = {
        "closed": True,
        "markets": [
            market("Loser", ["0", "1"]),
            market("Winner", ["1", "0"]),
            market("Placeholder 1", ["0", "1"], active=False),
        ],
    }
    assert result(event) == "Winner"


def test_inactive_other_outcome_can_win():
    event = {
        "closed": True,
        "markets": [
            market("ChatGPT", ["0", "1"]),
            market("Claude", ["0", "1"]),
            market("Other", ["1", "0"], active=False),
        ],
    }
    assert result(event) == "Other"


def test_single_market_result_is_outcome_name():
    event = {"closed": True, "markets": [market(None, ["0", "1"], outcomes=("Hike", "Cut"))]}
    assert result(event) == "Cut"


def test_open_or_unsettled_events_have_no_result():
    assert result({"closed": False, "markets": [market("A", ["1", "0"])]}) is None
    assert result({"closed": True, "markets": [market("A", ["0.6", "0.4"])]}) is None


def test_all_listed_outcomes_lost():
    event = {"closed": True, "markets": [market("A", ["0", "1"]), market("B", ["0", "1"])]}
    assert result(event) == "None of the listed outcomes"


def test_shape_ignores_dates_and_punctuation():
    assert shape("What will be the top US Netflix show this week? (November 3)") == shape(
        "What will be the top US Netflix show this week?"
    )
    assert shape("Steam Weekly #1 Seller (October 27 - November 3)") == shape(
        "Steam Weekly #1 Seller (November 3 - 10)"
    )
    assert shape("#1 Free App in the US Apple App Store on July 10?") != shape(
        "#2 Free App in the US Apple App Store on July 10?"
    )


def event(id_, title, end, **extra):
    return {"id": id_, "title": title, "endDate": end, "closed": True, "markets": [], **extra}


def test_history_merges_series_and_search_and_drops_strangers_and_drafts():
    current = event(1, "#1 Paid App in the US Apple App Store on November 6?", "2026-11-07", closed=False, series=[{"id": 9}])
    in_series = [
        current,
        event(2, "#1 Paid App in the US Apple App Store on October 30?", "2026-10-31"),
        event(3, "#2 Paid App in the US Apple App Store on October 30?", "2026-10-31"),
        event(4, "#1 Paid App in the US Apple App Store on March 27?", "2026-03-27", closed=False, active=False),
    ]
    orphan = event(5, "#1 Paid App in the US Apple App Store on December 5?", "2025-12-05")
    queries = []

    def handler(request):
        url = str(request.url)
        if "/events/1" in url:
            return httpx.Response(200, json=current)
        if "series_id" in url:
            return httpx.Response(200, json=in_series)
        queries.append((request.url.params["q"], request.url.params["events_status"], request.url.params["page"]))
        page = int(request.url.params["page"])
        found = [orphan, in_series[1]] if page == 1 else []
        return httpx.Response(200, json={"events": found, "pagination": {"hasMore": page == 1}})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_history(client, "1")

    history = asyncio.run(scenario())
    assert [item["id"] for item in history["events"]] == ["1", "2", "5"]
    assert queries[0] == ("#1 Paid App in the US Apple App Store on", "closed", "1")
    assert len(queries) == 4
