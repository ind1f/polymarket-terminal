import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

import httpx

log = logging.getLogger(__name__)

GAMMA_URL = "https://gamma-api.polymarket.com/markets"


async def fetch_top_tokens(client: httpx.AsyncClient, markets: int) -> set[str]:
    response = await client.get(
        GAMMA_URL,
        params={
            "active": "true",
            "closed": "false",
            "limit": markets,
            "order": "volume24hr",
            "ascending": "false",
        },
    )
    response.raise_for_status()
    tokens: set[str] = set()
    for market in response.json():
        if market.get("acceptingOrders") and market.get("clobTokenIds"):
            tokens.update(json.loads(market["clobTokenIds"]))
    return tokens


async def refresh_universe(
    apply: Callable[[set[str]], Awaitable[None]],
    markets: int,
    refresh_seconds: float,
) -> None:
    headers = {"User-Agent": "polymarket-terminal"}
    async with httpx.AsyncClient(headers=headers, timeout=20) as client:
        while True:
            try:
                await apply(await fetch_top_tokens(client, markets))
            except (httpx.HTTPError, ValueError) as error:
                log.warning("Universe refresh failed, keeping previous markets: %s", error)
            await asyncio.sleep(refresh_seconds)
