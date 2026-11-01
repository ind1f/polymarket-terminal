import { useEffect, useState } from "react";
import {
  fetchBook,
  fetchEvent,
  fetchEvents,
  fetchHistory,
  searchEvents,
  type Interval,
  type Market,
  type MarketEvent,
} from "./api";
import { cents, dollars } from "./format";
import { OrderBook } from "./OrderBook";
import { PriceChart } from "./PriceChart";
import { usePolling } from "./usePolling";

const INTERVALS: Interval[] = ["1d", "1w", "1m", "max"];

function flip(price: number | null): number | null {
  return price === null ? null : 1 - price;
}

function quote(market: Market, outcome: number) {
  if (outcome === 0) {
    return { price: market.price, bid: market.bestBid, ask: market.bestAsk, last: market.lastPrice };
  }
  return {
    price: flip(market.price),
    bid: flip(market.bestAsk),
    ask: flip(market.bestBid),
    last: flip(market.lastPrice),
  };
}

function topLine(event: MarketEvent): string {
  const top = event.markets[0];
  return event.markets.length > 1 ? `${top.label} ${cents(top.price)}` : cents(top.price);
}

export function App() {
  const events = usePolling(fetchEvents, "events", 300_000);
  const [selected, setSelected] = useState<MarketEvent | null>(null);
  const [marketId, setMarketId] = useState<string | null>(null);
  const [outcome, setOutcome] = useState(0);
  const [interval, setInterval] = useState<Interval>("1w");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const results = usePolling((signal) => searchEvents(query, signal), query || null, 30_000);
  const list = query ? results : events;
  const initial = selected ?? events.data?.[0] ?? null;
  const live = usePolling(
    (signal) => fetchEvent(initial!.id, signal),
    initial?.id ?? null,
    30_000,
  );

  const event = live.data?.id === initial?.id ? (live.data ?? initial) : initial;
  const market =
    event?.markets.find((candidate) => candidate.id === marketId) ?? event?.markets[0] ?? null;
  const token = market?.tokens[outcome] ?? null;

  const book = usePolling((signal) => fetchBook(token!, signal), token, 2_000);
  const historyKey = token && `${token}:${interval}`;
  const history = usePolling(
    (signal) => fetchHistory(token!, interval, signal),
    historyKey,
    60_000,
  );

  const selectEvent = (next: MarketEvent) => {
    setSelected(next);
    setMarketId(next.markets[0].id);
    setOutcome(0);
  };

  const selectMarket = (next: Market) => {
    setSelected(event);
    setMarketId(next.id);
  };

  const bestBid = book.data?.bids[0]?.price ?? null;
  const bestAsk = book.data?.asks[0]?.price ?? null;

  return (
    <div className="app">
      <header className="topbar">
        <strong>Polymarket Terminal</strong>
        <span className="badge">Read-only</span>
        <span className="muted topbar-status">
          {book.error
            ? `Book error: ${book.error}`
            : book.data && `Book ${new Date(book.data.timestamp).toLocaleTimeString()}`}
        </span>
      </header>

      <aside className="panel markets">
        <input
          className="search"
          type="search"
          placeholder="Search all markets"
          aria-label="Search markets"
          value={search}
          onChange={(change) => setSearch(change.target.value)}
        />
        <div className="market-list">
          {list.error && !list.data && (
            <p className="message">Couldn't load markets: {list.error}</p>
          )}
          {!list.data && !list.error && <p className="message">Loading markets…</p>}
          {list.data?.length === 0 && <p className="message">No matches</p>}
          {list.data?.map((candidate) => (
            <button
              className={`market-row ${candidate.id === event?.id ? "active" : ""}`}
              key={candidate.id}
              onClick={() => selectEvent(candidate)}
            >
              <span className="market-question">{candidate.title}</span>
              <span className="market-meta">
                <span className="market-top">{topLine(candidate)}</span>
                <span className="muted market-volume">{dollars(candidate.volume24h)} 24h</span>
              </span>
            </button>
          ))}
        </div>
      </aside>

      <main className="panel detail">
        {event && market ? (
          <>
            <h1>{event.title}</h1>
            <div className="stats-row">
              <dl className="stats">
                <div>
                  <dt>Bid</dt>
                  <dd>{cents(bestBid)}</dd>
                </div>
                <div>
                  <dt>Ask</dt>
                  <dd>{cents(bestAsk)}</dd>
                </div>
                <div>
                  <dt>Last</dt>
                  <dd>{cents(market && quote(market, outcome).last)}</dd>
                </div>
                <div>
                  <dt>24h volume</dt>
                  <dd>{dollars(event.volume24h)}</dd>
                </div>
                <div>
                  <dt>Liquidity</dt>
                  <dd>{dollars(event.liquidity)}</dd>
                </div>
                <div>
                  <dt>Ends</dt>
                  <dd>{event.endDate ? new Date(event.endDate).toLocaleDateString() : "–"}</dd>
                </div>
              </dl>
              <div className="tabs" role="group" aria-label="Outcome">
                {market.outcomes.map((name, index) => (
                  <button
                    key={name}
                    className={index === outcome ? "active" : ""}
                    onClick={() => setOutcome(index)}
                  >
                    {name}
                  </button>
                ))}
              </div>
            </div>
            {event.markets.length > 1 && (
              <div className="outcomes">
                <div className="outcome-row outcome-head">
                  <span>Outcome</span>
                  <span>{market.outcomes[outcome]}</span>
                  <span>Bid</span>
                  <span>Ask</span>
                  <span>24h</span>
                </div>
                {event.markets.map((candidate) => {
                  const active = candidate.id === market.id;
                  const row = quote(candidate, outcome);
                  return (
                    <button
                      className={`outcome-row ${active ? "active" : ""}`}
                      key={candidate.id}
                      onClick={() => selectMarket(candidate)}
                    >
                      <span>{candidate.label}</span>
                      <span>{cents(row.price)}</span>
                      <span>{cents(active && book.data ? bestBid : row.bid)}</span>
                      <span>{cents(active && book.data ? bestAsk : row.ask)}</span>
                      <span>{dollars(candidate.volume24h)}</span>
                    </button>
                  );
                })}
              </div>
            )}
            <div className="chart-head">
              <span className="muted chart-label">
                {event.markets.length > 1 && `${market.label}: `}
                {market.outcomes[outcome]} price
              </span>
              <div className="tabs" role="group" aria-label="Time range">
                {INTERVALS.map((value) => (
                  <button
                    key={value}
                    className={value === interval ? "active" : ""}
                    onClick={() => setInterval(value)}
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>
            <div className="chart-wrap">
              <PriceChart points={history.data ?? []} resetKey={historyKey ?? ""} />
              {history.error && !history.data && (
                <p className="message overlay">Couldn't load history: {history.error}</p>
              )}
              {history.data?.length === 0 && (
                <p className="message overlay">No price history for this range</p>
              )}
            </div>
          </>
        ) : (
          <p className="message">Select a market</p>
        )}
      </main>

      <aside className="panel book-panel">
        <h2>Order book</h2>
        {book.error && !book.data && <p className="message">Couldn't load book: {book.error}</p>}
        {!book.data && !book.error && <p className="message">Loading book…</p>}
        {book.data && <OrderBook book={book.data} />}
      </aside>
    </div>
  );
}
