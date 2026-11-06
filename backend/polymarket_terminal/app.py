import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from polymarket_terminal.alerts import AlertLoop, RankAlerts, Telegram
from polymarket_terminal.envfile import load_env
from polymarket_terminal.feed import Feed
from polymarket_terminal.rankings import CHARTS, FETCH_ERRORS, Rankings
from polymarket_terminal.series import HistoryCache
from polymarket_terminal.snapshots import Snapshotter, collect
from polymarket_terminal.recorder import Recorder
from polymarket_terminal.universe import refresh_universe

load_env()

FEED_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parents[2] / "data" / "raw"))
RECORD_DATA = os.environ.get("RECORD_DATA") == "1"
RECORD_MARKETS = int(os.environ.get("RECORD_MARKETS", "50"))
MIN_FREE_GB = float(os.environ.get("MIN_FREE_GB", "5"))
RANK_SNAPSHOTS = os.environ.get("RANK_SNAPSHOTS", "1") == "1"
SNAPSHOT_PATH = Path(__file__).parents[2] / "data" / "rankings" / "appstore.csv"
ALERT_STATE_PATH = SNAPSHOT_PATH.with_name("alerts.json")
APP_ALERTS = [app_id.strip() for app_id in os.environ.get("APP_ALERTS", "6462904878").split(",") if app_id.strip()]
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ALERT_INTERVAL_SECONDS = float(os.environ.get("ALERT_INTERVAL_SECONDS", "60"))
UNIVERSE_REFRESH_SECONDS = 600
STREAM_INTERVAL_SECONDS = 0.1
QUOTE_INTERVAL_SECONDS = 0.25
MAX_QUOTE_TOKENS = 1000

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    recorder = Recorder(DATA_DIR, min_free_bytes=int(MIN_FREE_GB * 1024**3)) if RECORD_DATA else None
    feed = Feed(FEED_URL, recorder.add if recorder else lambda _received, _event: None)
    app.state.recorder = recorder
    app.state.feed = feed
    client = httpx.AsyncClient(timeout=20)
    app.state.rankings = Rankings(client)
    app.state.history = HistoryCache(client)
    tasks = [asyncio.create_task(feed.run())]
    app.state.alerts = (
        RankAlerts(Telegram(client, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID), APP_ALERTS, ALERT_STATE_PATH)
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID and APP_ALERTS
        else None
    )
    if app.state.alerts is None:
        logging.getLogger(__name__).info("Telegram alerts off: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
    app.state.snapshots = Snapshotter(app.state.rankings, SNAPSHOT_PATH) if RANK_SNAPSHOTS else None
    app.state.alert_loop = (
        AlertLoop(
            app.state.alerts,
            lambda now: collect(app.state.rankings, now),
            ALERT_INTERVAL_SECONDS,
        )
        if app.state.alerts
        else None
    )
    if app.state.snapshots:
        tasks.append(asyncio.create_task(app.state.snapshots.run()))
    if app.state.alert_loop:
        tasks.append(asyncio.create_task(app.state.alert_loop.run()))
    if recorder:
        tasks.append(asyncio.create_task(recorder.run()))
        tasks.append(
            asyncio.create_task(
                refresh_universe(feed.set_universe, RECORD_MARKETS, UNIVERSE_REFRESH_SECONDS)
            )
        )
    yield
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    if recorder:
        await recorder.flush()
    await client.aclose()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    feed: Feed = app.state.feed
    recorder: Recorder | None = app.state.recorder
    status = {
        "connected": feed.connected,
        "reconnects": feed.reconnects,
        "tokens": feed.token_count,
        "books": len(feed.books),
        "recording": recorder is not None,
    }
    snapshots: Snapshotter | None = app.state.snapshots
    if snapshots:
        status["rank_snapshots"] = {
            "last": snapshots.last.isoformat() if snapshots.last else None,
            "rows": snapshots.last_rows,
            "error": snapshots.last_error,
        }
    alerts: RankAlerts | None = app.state.alerts
    loop: AlertLoop | None = app.state.alert_loop
    status["telegram_alerts"] = (
        {
            "watching": alerts.app_ids,
            "every_seconds": ALERT_INTERVAL_SECONDS,
            "last_check": loop.last_check.isoformat() if loop and loop.last_check else None,
            "sent": alerts.sent,
            "error": alerts.last_error,
        }
        if alerts
        else "off"
    )
    if recorder:
        status |= {
            "rows_written": recorder.rows_written,
            "rows_buffered": recorder.buffered,
            "rows_dropped": recorder.rows_dropped,
            "files_written": recorder.files_written,
            "recorder_error": recorder.last_error,
        }
    return status


@app.get("/api/rankings/{chart_id}")
async def ranking(chart_id: str) -> dict:
    if chart_id not in CHARTS:
        raise HTTPException(status_code=404, detail="Unknown chart")
    rankings: Rankings = app.state.rankings
    try:
        return await rankings.get(chart_id)
    except FETCH_ERRORS as error:
        raise HTTPException(status_code=502, detail="Ranking source unavailable") from error


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


@app.get("/api/history/{event_id}")
async def history(event_id: str) -> dict:
    if not event_id.isdigit():
        raise HTTPException(status_code=404, detail="Unknown event")
    cache: HistoryCache = app.state.history
    try:
        return await cache.get(event_id)
    except (httpx.HTTPError, KeyError, ValueError) as error:
        raise HTTPException(status_code=502, detail="History unavailable") from error


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
