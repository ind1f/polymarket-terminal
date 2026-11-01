import asyncio
import json
import logging
import time
from collections import Counter
from collections.abc import Callable

import websockets

from polymarket_terminal.book import Book

log = logging.getLogger(__name__)

OnEvent = Callable[[int, dict], None]
Listener = Callable[[], None]


def now_ms() -> int:
    return time.time_ns() // 1_000_000


class Feed:
    def __init__(
        self,
        url: str,
        on_event: OnEvent,
        ping_seconds: float = 10,
        stale_seconds: float = 30,
        max_backoff_seconds: float = 30,
    ) -> None:
        self.url = url
        self.on_event = on_event
        self.ping_seconds = ping_seconds
        self.stale_seconds = stale_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.books: dict[str, Book] = {}
        self.connected = False
        self.reconnects = 0
        self._universe: set[str] = set()
        self._watch_counts: Counter[str] = Counter()
        self._listeners: dict[str, set[Listener]] = {}
        self._subscribed: set[str] = set()
        self._socket = None
        self._has_tokens = asyncio.Event()

    @property
    def token_count(self) -> int:
        return len(self._subscribed)

    async def set_universe(self, tokens: set[str]) -> None:
        self._universe = tokens
        await self._sync()

    async def watch(self, token: str, listener: Listener) -> None:
        self._watch_counts[token] += 1
        self._listeners.setdefault(token, set()).add(listener)
        await self._sync()

    async def unwatch(self, token: str, listener: Listener) -> None:
        self._watch_counts[token] -= 1
        if self._watch_counts[token] <= 0:
            del self._watch_counts[token]
        listeners = self._listeners.get(token, set())
        listeners.discard(listener)
        if not listeners:
            self._listeners.pop(token, None)
        await self._sync()

    def view(self, token: str) -> dict:
        book = self.books.get(token)
        return {"connected": self.connected, "book": book.view() if book else None}

    def _desired(self) -> set[str]:
        return self._universe | set(self._watch_counts)

    async def _sync(self) -> None:
        desired = self._desired()
        if desired:
            self._has_tokens.set()
        if self._socket is None:
            return
        added = desired - self._subscribed
        removed = self._subscribed - desired
        try:
            if added:
                await self._socket.send(
                    json.dumps({"assets_ids": sorted(added), "operation": "subscribe"})
                )
            if removed:
                await self._socket.send(
                    json.dumps({"assets_ids": sorted(removed), "operation": "unsubscribe"})
                )
        except websockets.ConnectionClosed:
            return
        self._subscribed = desired
        for token in removed:
            self.books.pop(token, None)

    async def run(self) -> None:
        backoff = 1.0
        while True:
            await self._has_tokens.wait()
            started = time.monotonic()
            try:
                async with websockets.connect(self.url, ping_interval=None, max_size=None) as socket:
                    await self._session(socket)
            except asyncio.CancelledError:
                raise
            except (OSError, TimeoutError, websockets.WebSocketException) as error:
                log.warning("Feed connection lost: %s", error)
            self._mark_disconnected()
            if time.monotonic() - started > 60:
                backoff = 1.0
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self.max_backoff_seconds)

    async def _session(self, socket) -> None:
        desired = self._desired()
        await socket.send(json.dumps({"assets_ids": sorted(desired), "type": "market"}))
        self._socket = socket
        self._subscribed = desired
        self.connected = True
        self.on_event(now_ms(), {"event_type": "feed_connected", "tokens": len(desired)})
        log.info("Feed connected with %d tokens", len(desired))
        self._notify_all()
        await self._sync()
        pinger = asyncio.create_task(self._ping(socket))
        try:
            while True:
                raw = await asyncio.wait_for(socket.recv(), self.stale_seconds)
                self.handle(raw)
        finally:
            pinger.cancel()

    async def _ping(self, socket) -> None:
        while True:
            await asyncio.sleep(self.ping_seconds)
            await socket.send("PING")

    def _mark_disconnected(self) -> None:
        self._socket = None
        self._subscribed = set()
        if not self.connected:
            return
        self.connected = False
        self.reconnects += 1
        self.on_event(now_ms(), {"event_type": "feed_disconnected"})
        self._notify_all()

    def handle(self, raw: str | bytes) -> None:
        if raw in ("PONG", "pong"):
            return
        try:
            data = json.loads(raw)
        except ValueError:
            log.warning("Unparseable feed message: %.200s", raw)
            return
        received = now_ms()
        for event in data if isinstance(data, list) else [data]:
            self.on_event(received, event)
            self._apply(event)

    def _apply(self, event: dict) -> None:
        kind = event.get("event_type")
        if kind == "book":
            token = event["asset_id"]
            self.books.setdefault(token, Book()).apply_snapshot(event)
            self._notify(token)
        elif kind == "price_change":
            timestamp = int(event["timestamp"]) if event.get("timestamp") else None
            for change in event.get("price_changes", []):
                token = change["asset_id"]
                book = self.books.get(token)
                if book is None:
                    continue
                book.apply_change(change, timestamp)
                self._notify(token)

    def _notify(self, token: str) -> None:
        for listener in self._listeners.get(token, ()):
            listener()

    def _notify_all(self) -> None:
        for token in self._listeners:
            self._notify(token)
