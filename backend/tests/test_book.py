from polymarket_terminal.book import Book


def snapshot() -> Book:
    book = Book()
    book.apply_snapshot(
        {
            "timestamp": "100",
            "bids": [{"price": "0.01", "size": "5"}, {"price": "0.25", "size": "10"}],
            "asks": [{"price": "0.99", "size": "7"}, {"price": "0.26", "size": "3"}],
        }
    )
    return book


def test_view_puts_best_prices_first():
    view = snapshot().view()
    assert [level["price"] for level in view["bids"]] == [0.25, 0.01]
    assert [level["price"] for level in view["asks"]] == [0.26, 0.99]
    assert view["timestamp"] == 100


def test_change_replaces_level_size():
    book = snapshot()
    book.apply_change({"side": "BUY", "price": "0.25", "size": "42"}, 200)
    assert book.view()["bids"][0] == {"price": 0.25, "size": 42.0}
    assert book.timestamp == 200


def test_change_adds_new_level_on_correct_side():
    book = snapshot()
    book.apply_change({"side": "SELL", "price": "0.255", "size": "1"}, None)
    assert book.view()["asks"][0] == {"price": 0.255, "size": 1.0}
    assert book.timestamp == 100


def test_zero_size_removes_level_and_missing_level_is_ignored():
    book = snapshot()
    book.apply_change({"side": "BUY", "price": "0.25", "size": "0"}, None)
    book.apply_change({"side": "BUY", "price": "0.5", "size": "0.0"}, None)
    assert [level["price"] for level in book.view()["bids"]] == [0.01]


def test_snapshot_discards_previous_levels():
    book = snapshot()
    book.apply_snapshot({"timestamp": "300", "bids": [], "asks": []})
    assert book.view() == {"bids": [], "asks": [], "timestamp": 300}


def test_depth_limits_levels():
    assert len(snapshot().view(depth=1)["bids"]) == 1
