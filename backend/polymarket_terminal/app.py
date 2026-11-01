import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket

from polymarket_terminal.feed import Feed
from polymarket_terminal.recorder import Recorder
from polymarket_terminal.universe import refresh_universe

FEED_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parents[2] / "data" / "raw"))
RECORD_MARKETS = int(os.environ.get("RECORD_MARKETS", "50"))
MIN_FREE_GB = float(os.environ.get("MIN_FREE_GB", "5"))
UNIVERSE_REFRESH_SECONDS = 600
STREAM_INTERVAL_SECONDS = 0.1

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    recorder = Recorder(DATA_DIR, min_free_bytes=int(MIN_FREE_GB * 1024**3))
    feed = Feed(FEED_URL, recorder.add)
    app.state.recorder = recorder
    app.state.feed = feed
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


@app.websocket("/ws/book/{token}")
async def stream_book(socket: WebSocket, token: str) -> None:
    feed: Feed = app.state.feed
    await socket.accept()
    changed = asyncio.Event()
    changed.set()
    await feed.watch(token, changed.set)

    async def send() -> None:
        while True:
            await changed.wait()
            changed.clear()
            await socket.send_json(feed.view(token))
            await asyncio.sleep(STREAM_INTERVAL_SECONDS)

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
        await feed.unwatch(token, changed.set)
