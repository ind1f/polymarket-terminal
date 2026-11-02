import asyncio

import httpx
import pytest

from polymarket_terminal.rankings import Chart, Rankings


def rankings_with(fetch, cache_seconds=60) -> Rankings:
    return Rankings(httpx.AsyncClient(), {"test": Chart(fetch, cache_seconds)})


def test_second_request_uses_cache():
    calls = []

    async def fetch(_client):
        calls.append(1)
        return {"rows": [], "fetched_ms": 10**13}

    async def scenario():
        rankings = rankings_with(fetch)
        first = await rankings.get("test")
        assert await rankings.get("test") is first
        assert first["id"] == "test"

    asyncio.run(scenario())
    assert len(calls) == 1


def test_failed_refresh_serves_last_good_chart():
    state = {"fail": False}

    async def fetch(_client):
        if state["fail"]:
            raise httpx.ConnectError("down")
        return {"rows": [1], "fetched_ms": 0}

    async def scenario():
        rankings = rankings_with(fetch, cache_seconds=0)
        good = await rankings.get("test")
        state["fail"] = True
        assert await rankings.get("test") is good

    asyncio.run(scenario())


def test_failure_without_cache_raises():
    async def fetch(_client):
        raise ValueError("changed format")

    with pytest.raises(ValueError):
        asyncio.run(rankings_with(fetch).get("test"))
