class Book:
    def __init__(self) -> None:
        self.bids: dict[str, str] = {}
        self.asks: dict[str, str] = {}
        self.timestamp: int | None = None

    def apply_snapshot(self, event: dict) -> None:
        self.bids = {level["price"]: level["size"] for level in event["bids"]}
        self.asks = {level["price"]: level["size"] for level in event["asks"]}
        self.timestamp = int(event["timestamp"])

    def apply_change(self, change: dict, timestamp: int | None) -> None:
        side = self.bids if change["side"] == "BUY" else self.asks
        if float(change["size"]) == 0:
            side.pop(change["price"], None)
        else:
            side[change["price"]] = change["size"]
        if timestamp is not None:
            self.timestamp = timestamp

    def quote(self) -> dict:
        return {
            "bid": max(map(float, self.bids), default=None),
            "ask": min(map(float, self.asks), default=None),
        }

    def view(self, depth: int = 50) -> dict:
        return {
            "bids": _levels(self.bids, reverse=True)[:depth],
            "asks": _levels(self.asks, reverse=False)[:depth],
            "timestamp": self.timestamp,
        }


def _levels(side: dict[str, str], reverse: bool) -> list[dict]:
    levels = [{"price": float(price), "size": float(size)} for price, size in side.items()]
    return sorted(levels, key=lambda level: level["price"], reverse=reverse)
