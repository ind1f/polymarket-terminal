import asyncio
import json

import httpx

from polymarket_terminal.alerts import RankAlerts
from polymarket_terminal.envfile import load_env, set_env_value


class FakeTelegram:
    def __init__(self):
        self.messages = []
        self.failing = False

    async def send(self, text):
        if self.failing:
            raise httpx.ConnectError("offline")
        self.messages.append(text)


FULL = {"free": 100, "paid": 100}


def row(chart, rank, app_id="42", name="BigFuture School"):
    return {"captured_at": "2026-11-04T18:00:00+00:00", "chart": chart, "rank": rank, "app_id": app_id, "name": name}


def chart(name_prefix, ids, chart_name="free", start=1):
    return [row(chart_name, start + i, app_id=str(app_id), name=f"{name_prefix}{app_id}") for i, app_id in enumerate(ids)]


TOP = list(range(1000, 1100))

def test_every_bigfuture_rank_change_is_reported(tmp_path):
    telegram = FakeTelegram()
    alerts = RankAlerts(telegram, ["42"], tmp_path / "alerts.json")
    asyncio.run(alerts.check(chart("App", TOP), FULL))
    assert telegram.messages == []
    asyncio.run(alerts.check(chart("App", TOP) + [row("free", 87)], FULL))
    assert "BigFuture School entered Top Free Apps at #87" in telegram.messages[-1]
    asyncio.run(alerts.check(chart("App", TOP) + [row("free", 87)], FULL))
    assert len(telegram.messages) == 1
    asyncio.run(alerts.check(chart("App", TOP) + [row("free", 72)], FULL))
    assert "BigFuture School ▲ Top Free Apps: #87 → #72" in telegram.messages[-1]
    asyncio.run(alerts.check(chart("App", TOP) + [row("free", 80)], FULL))
    assert "BigFuture School ▼ Top Free Apps: #72 → #80" in telegram.messages[-1]
    asyncio.run(alerts.check(chart("App", TOP), FULL))
    assert "App 42 left Top Free Apps (was #80)" in telegram.messages[-1]
    assert len(telegram.messages) == 4


def test_top_100_reports_real_movers_not_shifted_apps(tmp_path):
    telegram = FakeTelegram()
    alerts = RankAlerts(telegram, [], tmp_path / "alerts.json")
    asyncio.run(alerts.check(chart("App", TOP), FULL))
    assert telegram.messages == []
    after = TOP[:5] + [5000] + TOP[5:20] + [TOP[60]] + [app for app in TOP[20:99] if app != TOP[60]]
    assert len(after) == 100
    asyncio.run(alerts.check(chart("App", after), FULL))
    message = telegram.messages[-1]
    lines = message.splitlines()
    assert lines[0] == "Top Free Apps top 100:"
    assert "New: App5000 at #6" in message
    assert f"▲ App{TOP[60]}: #61 → #22" in message
    assert f"Out: App{TOP[99]} (was #100)" in message
    assert sum(line.startswith(("▲", "▼")) for line in lines) == 1
    asyncio.run(alerts.check(chart("App", after), FULL))
    assert len(telegram.messages) == 1


def test_steady_order_finds_apps_that_kept_relative_order():
    from polymarket_terminal.alerts import steady_order

    old = {"a": 1, "b": 2, "c": 3, "d": 4}
    assert set(steady_order(["a", "c", "d", "b"], old)) == {"a", "c", "d"}
    assert steady_order([], {}) == []


def test_long_messages_are_split_for_telegram():
    from polymarket_terminal.alerts import chunks

    text = "\n".join(f"line {i} " + "x" * 50 for i in range(200))
    parts = chunks(text, limit=1000)
    assert all(len(part) <= 1000 for part in parts)
    assert "\n".join(parts) == text


def test_changes_from_one_check_arrive_in_one_message(tmp_path):
    telegram = FakeTelegram()
    alerts = RankAlerts(telegram, ["42"], tmp_path / "alerts.json")
    asyncio.run(alerts.check(chart("App", TOP) + chart("Paid", TOP, "paid"), FULL))
    swapped = [101, 100] + TOP[2:]
    asyncio.run(alerts.check(chart("App", swapped) + chart("Paid", swapped, "paid") + [row("free", 50)], FULL))
    assert len(telegram.messages) == 1
    message = telegram.messages[0]
    assert "entered Top Free Apps at #50" in message
    assert "Top Free Apps top 100:" in message and "Top Paid Apps top 100:" in message


def test_failed_send_keeps_state_and_retries(tmp_path):
    telegram = FakeTelegram()
    alerts = RankAlerts(telegram, ["42"], tmp_path / "alerts.json")
    asyncio.run(alerts.check(chart("App", TOP), FULL))
    telegram.failing = True
    asyncio.run(alerts.check(chart("App", TOP) + [row("free", 87)], FULL))
    assert alerts.last_error
    telegram.failing = False
    asyncio.run(alerts.check(chart("App", TOP) + [row("free", 87)], FULL))
    assert "entered Top Free Apps at #87" in telegram.messages[-1]


def test_state_survives_restart_and_old_format_is_migrated(tmp_path):
    path = tmp_path / "alerts.json"
    path.write_text(json.dumps({"42": {"free": 87}}))
    telegram = FakeTelegram()
    alerts = RankAlerts(telegram, ["42"], path)
    asyncio.run(alerts.check(chart("App", TOP) + [row("free", 87)], FULL))
    assert telegram.messages == []
    second = FakeTelegram()
    asyncio.run(RankAlerts(second, ["42"], path).check(chart("App", TOP) + [row("free", 85)], FULL))
    assert "#87 → #85" in second.messages[0]


def test_partial_or_missing_chart_does_not_count_as_leaving(tmp_path):
    telegram = FakeTelegram()
    alerts = RankAlerts(telegram, ["42"], tmp_path / "alerts.json")
    with_app = chart("App", TOP[:59]) + [row("free", 60)] + chart("App", TOP[59:99], start=61)
    asyncio.run(alerts.check(with_app, FULL))
    asyncio.run(alerts.check(chart("App", TOP[:25]), {"free": 25, "paid": 100}))
    asyncio.run(alerts.check([], {"paid": 100}))
    asyncio.run(alerts.check(with_app, FULL))
    assert len(telegram.messages) == 1


def test_env_file_loading_and_update(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text('# comment\nTELEGRAM_BOT_TOKEN="abc:123"\nTELEGRAM_CHAT_ID=1\n')
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    load_env(path)
    import os
    assert os.environ["TELEGRAM_BOT_TOKEN"] == "abc:123"
    set_env_value("TELEGRAM_CHAT_ID", "999", path)
    assert path.read_text().splitlines()[-1] == "TELEGRAM_CHAT_ID=999"
    assert sum("TELEGRAM_CHAT_ID" in line for line in path.read_text().splitlines()) == 1


def test_alert_loop_checks_on_its_interval():
    calls = []

    class Alerts:
        async def check(self, rows, counts):
            calls.append(counts)

    async def collect(now):
        return [], {"free": 100}

    async def scenario():
        from polymarket_terminal.alerts import AlertLoop

        loop = AlertLoop(Alerts(), collect, interval_seconds=0.05, tick_seconds=0.01)
        task = asyncio.create_task(loop.run())
        await asyncio.sleep(0.18)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return loop

    loop = asyncio.run(scenario())
    assert 3 <= len(calls) <= 5
    assert loop.last_check is not None


def test_alert_loop_uses_wall_clock_so_sleep_cannot_stall_it(monkeypatch):
    from datetime import UTC, datetime, timedelta

    from polymarket_terminal import alerts as alerts_module
    from polymarket_terminal.alerts import AlertLoop

    clock = {"now": datetime(2026, 11, 5, 12, 0, tzinfo=UTC)}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["now"]

    monkeypatch.setattr(alerts_module, "datetime", Clock)
    calls = []

    class Alerts:
        async def check(self, rows, counts):
            calls.append(clock["now"])

    async def collect(now):
        return [], {"free": 100}

    async def scenario():
        loop = AlertLoop(Alerts(), collect, interval_seconds=300, tick_seconds=0.01)
        task = asyncio.create_task(loop.run())
        await asyncio.sleep(0.05)
        clock["now"] += timedelta(hours=3)
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
    assert len(calls) == 2


def test_saved_state_of_a_different_size_starts_fresh_silently(tmp_path):
    path = tmp_path / "alerts.json"
    path.write_text(json.dumps({"apps": {}, "top": {"free": [[str(app), f"App{app}"] for app in TOP[:10]]}}))
    telegram = FakeTelegram()
    alerts = RankAlerts(telegram, [], path)
    asyncio.run(alerts.check(chart("App", TOP), FULL))
    assert telegram.messages == []
    assert len(json.loads(path.read_text())["top"]["free"]) == 100
