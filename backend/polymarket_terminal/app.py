import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from polymarket_terminal.appstore import AppStoreCharts
from polymarket_terminal.feed import Feed
from polymarket_terminal.recorder import Recorder
from polymarket_terminal.universe import refresh_universe

FEED_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parents[2] / "data" / "raw"))
RECORD_MARKETS = int(os.environ.get("RECORD_MARKETS", "50"))
MIN_FREE_GB = float(os.environ.get("MIN_FREE_GB", "5"))
UNIVERSE_REFRESH_SECONDS = 600
STREAM_INTERVAL_SECONDS = 0.1
QUOTE_INTERVAL_SECONDS = 0.25
MAX_QUOTE_TOKENS = 1000

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    recorder = Recorder(DATA_DIR, min_free_bytes=int(MIN_FREE_GB * 1024**3))
    feed = Feed(FEED_URL, recorder.add)
    app.state.recorder = recorder
    app.state.feed = feed
    client = httpx.AsyncClient(timeout=20)
    app.state.app_store = AppStoreCharts(client)
    tasks = [
        asyncio.create_task(feed.run()),
        asyncio.create_task(recorder.run()),
        asyncio.create_task(
            refresh_universe(feed.set_universe, RECORD_MARKETS, UNIVERSE_REFRESH_SECONDS)
        ),
    ]
    yield
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await recorder.flush()
    await client.aclose()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    feed: Feed = app.state.feed
    recorder: Recorder = app.state.recorder
    return {
        "connected": feed.connected,
        "reconnects": feed.reconnects,
        "tokens": feed.token_count,
        "books": len(feed.books),
        "rows_written": recorder.rows_written,
        "rows_buffered": recorder.buffered,
        "rows_dropped": recorder.rows_dropped,
        "files_written": recorder.files_written,
        "recorder_error": recorder.last_error,
    }


@app.get("/api/app-store/{chart}")
async def app_store_chart(chart: Literal["free", "paid"]) -> dict:
    charts: AppStoreCharts = app.state.app_store
    try:
        return await charts.get(chart)
    except (httpx.HTTPError, AttributeError, KeyError, StopIteration, ValueError) as error:
        raise HTTPException(status_code=502, detail="App Store unavailable") from error


async def run_until_disconnect(socket: WebSocket, send: Callable[[], Awaitable[None]]) -> None:
    async def receive() -> None:
        while True:
            await socket.receive_text()

    tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@app.websocket("/ws/book/{token}")
async def stream_book(socket: WebSocket, token: str) -> None:
    feed: Feed = app.state.feed
    await socket.accept()
    changed = asyncio.Event()
    changed.set()
    await feed.watch([token], changed.set)

    async def send() -> None:
        while True:
            await changed.wait()
            changed.clear()
            await socket.send_json(feed.view(token))
            await asyncio.sleep(STREAM_INTERVAL_SECONDS)

    try:
        await run_until_disconnect(socket, send)
    finally:
        await feed.unwatch([token], changed.set)


@app.websocket("/ws/quotes")
async def stream_quotes(socket: WebSocket) -> None:
    feed: Feed = app.state.feed
    await socket.accept()
    try:
        tokens = list(TypeAdapter(list[str]).validate_python(await socket.receive_json()))
    except (ValidationError, ValueError):
        await socket.close(code=1003)
        return
    except WebSocketDisconnect:
        return
    if len(tokens) > MAX_QUOTE_TOKENS:
        await socket.close(code=1009)
        return
    changed = asyncio.Event()
    changed.set()
    await feed.watch(tokens, changed.set)

    async def send() -> None:
        sent: dict[str, dict] = {}
        connected = None
        while True:
            await changed.wait()
            changed.clear()
            quotes = feed.quotes(tokens)
            updates = {token: quote for token, quote in quotes.items() if sent.get(token) != quote}
            if updates or feed.connected != connected:
                connected = feed.connected
                sent |= updates
                await socket.send_json({"connected": connected, "quotes": updates})
            await asyncio.sleep(QUOTE_INTERVAL_SECONDS)

    try:
        await run_until_disconnect(socket, send)
    finally:
        await feed.unwatch(tokens, changed.set)
