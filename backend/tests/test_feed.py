import asyncio
import json

import websockets

from polymarket_terminal.feed import Feed


def book_event(token: str, bid: str) -> dict:
    return {
        "event_type": "book",
        "market": "0xabc",
        "asset_id": token,
        "timestamp": "100",
        "bids": [{"price": bid, "size": "10"}],
        "asks": [{"price": "0.9", "size": "4"}],
    }


def change_event(token: str) -> dict:
    return {
        "event_type": "price_change",
        "market": "0xabc",
        "timestamp": "200",
        "price_changes": [{"asset_id": token, "price": "0.5", "size": "9", "side": "BUY"}],
    }


def make_feed(url: str = "ws://unused") -> tuple[Feed, list[dict]]:
    events: list[dict] = []
    return Feed(url, lambda _, event: events.append(event), max_backoff_seconds=0.05), events


def tracking(*tokens: str) -> tuple[Feed, list[dict]]:
    feed, events = make_feed()
    asyncio.run(feed.watch(list(tokens), lambda: None))
    return feed, events


def test_handles_lists_single_events_pongs_and_garbage():
    feed, events = tracking("a")
    feed.handle(json.dumps([book_event("a", "0.4")]))
    feed.handle(json.dumps(change_event("a")))
    feed.handle("PONG")
    feed.handle("not json")
    assert [event["event_type"] for event in events] == ["book", "price_change"]
    assert feed.view("a")["book"]["bids"][0] == {"price": 0.5, "size": 9.0}
    assert feed.view("a")["book"]["timestamp"] == 200


def test_change_before_snapshot_is_recorded_but_not_applied():
    feed, events = tracking("a")
    feed.handle(json.dumps(change_event("a")))
    assert len(events) == 1
    assert feed.view("a")["book"] is None


def test_snapshots_for_untracked_tokens_are_recorded_but_not_stored():
    async def scenario():
        feed, events = make_feed()
        feed.handle(json.dumps([book_event("stray", "0.4")]))
        assert "stray" not in feed.books
        assert len(events) == 1

        listener = lambda: None
        await feed.watch(["a"], listener)
        feed.handle(json.dumps([book_event("a", "0.4")]))
        assert "a" in feed.books
        await feed.unwatch(["a"], listener)
        feed.handle(json.dumps([book_event("a", "0.5")]))
        assert "a" not in feed.books

    asyncio.run(scenario())


def test_listeners_only_hear_their_token():
    async def scenario():
        feed, _ = make_feed()
        calls = []
        listener = lambda: calls.append(1)
        await feed.watch(["a"], listener)
        feed.handle(json.dumps(book_event("b", "0.4")))
        assert calls == []
        feed.handle(json.dumps(book_event("a", "0.4")))
        assert calls == [1]
        await feed.unwatch(["a"], listener)
        feed.handle(json.dumps(book_event("a", "0.4")))
        assert calls == [1]

    asyncio.run(scenario())


def test_quotes_cover_only_tokens_with_books():
    feed, _ = tracking("a")
    feed.handle(json.dumps([book_event("a", "0.4")]))
    assert feed.quotes(["a", "missing"]) == {"a": {"bid": 0.4, "ask": 0.9}}


def test_watching_many_tokens_subscribes_once():
    async def scenario():
        received = []
        ready = asyncio.Event()

        async def server(socket):
            async for raw in socket:
                if raw != "PING":
                    received.append(json.loads(raw))
                    if len(received) == 2:
                        ready.set()

        async with websockets.serve(server, "127.0.0.1", 0) as listening:
            port = listening.sockets[0].getsockname()[1]
            feed, _ = make_feed(f"ws://127.0.0.1:{port}")
            await feed.set_universe({"u"})
            runner = asyncio.create_task(feed.run())
            async with asyncio.timeout(5):
                while not feed.connected:
                    await asyncio.sleep(0.01)
                listener = lambda: None
                await feed.watch(["a", "b", "a"], listener)
                await ready.wait()
            assert received[1] == {"assets_ids": ["a", "b"], "operation": "subscribe"}
            await feed.unwatch(["a", "b", "a"], listener)
            assert feed.token_count == 1
            runner.cancel()
            await asyncio.gather(runner, return_exceptions=True)

    asyncio.run(scenario())


def test_waits_for_tokens_again_after_last_watcher_leaves():
    async def scenario():
        connections = 0

        async def server(socket):
            nonlocal connections
            connections += 1
            await socket.recv()

        async with websockets.serve(server, "127.0.0.1", 0) as listening:
            port = listening.sockets[0].getsockname()[1]
            feed, _ = make_feed(f"ws://127.0.0.1:{port}")
            runner = asyncio.create_task(feed.run())
            await asyncio.sleep(0.05)
            assert connections == 0

            listener = lambda: None
            await feed.watch(["a"], listener)
            async with asyncio.timeout(5):
                while connections == 0:
                    await asyncio.sleep(0.01)
            await feed.unwatch(["a"], listener)
            await asyncio.sleep(0.3)
            assert connections == 1
            runner.cancel()
            await asyncio.gather(runner, return_exceptions=True)

    asyncio.run(scenario())


def test_reconnects_resubscribes_and_tracks_changes():
    async def scenario():
        received: list[list[dict]] = []
        connections = 0

        async def server(socket):
            nonlocal connections
            connections += 1
            current = connections
            messages: list[dict] = []
            received.append(messages)
            messages.append(json.loads(await socket.recv()))
            await socket.send(json.dumps([book_event("a", f"0.{current}")]))
            if current == 1:
                await socket.close()
                return
            async for raw in socket:
                if raw != "PING":
                    messages.append(json.loads(raw))
                    await socket.send(json.dumps([book_event("c", "0.3")]))

        async with websockets.serve(server, "127.0.0.1", 0) as listening:
            port = listening.sockets[0].getsockname()[1]
            feed, events = make_feed(f"ws://127.0.0.1:{port}")
            statuses: list[bool] = []
            await feed.watch(["a"], lambda: statuses.append(feed.connected))
            await feed.set_universe({"b"})
            runner = asyncio.create_task(feed.run())

            async def until(check):
                async with asyncio.timeout(5):
                    while not check():
                        await asyncio.sleep(0.01)

            await until(lambda: connections == 2 and feed.connected and "a" in feed.books)
            assert received[0][0] == {"assets_ids": ["a", "b"], "type": "market"}
            assert received[1][0] == {"assets_ids": ["a", "b"], "type": "market"}
            assert feed.reconnects == 1
            assert False in statuses
            await until(lambda: feed.view("a")["book"]["bids"][0]["price"] == 0.2)

            await feed.set_universe({"c"})
            await until(lambda: "c" in feed.books)
            assert received[1][1] == {"assets_ids": ["c"], "operation": "subscribe"}
            assert received[1][2] == {"assets_ids": ["b"], "operation": "unsubscribe"}
            assert feed.token_count == 2

            kinds = [event["event_type"] for event in events]
            assert kinds.count("feed_connected") == 2
            assert kinds.count("feed_disconnected") == 1
            runner.cancel()
            await asyncio.gather(runner, return_exceptions=True)

    asyncio.run(scenario())
