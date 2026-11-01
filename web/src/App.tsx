import { useEffect, useState } from "react";
import {
  fetchBook,
  fetchHistory,
  fetchMarket,
  fetchMarkets,
  searchMarkets,
  type Interval,
  type Market,
} from "./api";
import { cents, dollars } from "./format";
import { OrderBook } from "./OrderBook";
import { PriceChart } from "./PriceChart";
import { usePolling } from "./usePolling";

const INTERVALS: Interval[] = ["1d", "1w", "1m", "max"];

export function App() {
  const markets = usePolling(fetchMarkets, "markets", 30_000);
  const [selected, setSelected] = useState<Market | null>(null);
  const [outcome, setOutcome] = useState(0);
  const [interval, setInterval] = useState<Interval>("1w");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const results = usePolling((signal) => searchMarkets(query, signal), query || null, 30_000);
  const list = query ? results : markets;
  const live = usePolling(
    (signal) => fetchMarket(selected!.id, signal),
    selected?.id ?? null,
    30_000,
  );

  const market =
    (live.data?.id === selected?.id ? live.data : selected) ?? markets.data?.[0] ?? null;
  const token = market?.tokens[outcome] ?? null;

  const book = usePolling((signal) => fetchBook(token!, signal), token, 2_000);
  const historyKey = token && `${token}:${interval}`;
  const history = usePolling(
    (signal) => fetchHistory(token!, interval, signal),
    historyKey,
    60_000,
  );

  const bestBid = book.data?.bids[0]?.price ?? null;
  const bestAsk = book.data?.asks[0]?.price ?? null;
  const lastPrice =
    market?.lastPrice != null && outcome === 1 ? 1 - market.lastPrice : (market?.lastPrice ?? null);

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
          onChange={(event) => setSearch(event.target.value)}
        />
        <div className="market-list">
          {list.error && !list.data && (
            <p className="message">Couldn't load markets: {list.error}</p>
          )}
          {!list.data && !list.error && <p className="message">Loading markets…</p>}
          {list.data?.length === 0 && <p className="message">No matches</p>}
          {list.data?.map((candidate) => (
            <button
              className={`market-row ${candidate.id === market?.id ? "active" : ""}`}
              key={candidate.id}
              onClick={() => {
                setSelected(candidate);
                setOutcome(0);
              }}
            >
              <span className="market-question">{candidate.question}</span>
              <span className="market-meta">
                <span>{cents(candidate.lastPrice)}</span>
                <span className="muted">{dollars(candidate.volume24h)} 24h</span>
              </span>
            </button>
          ))}
        </div>
      </aside>

      <main className="panel detail">
        {market ? (
          <>
            <div className="detail-head">
              <h1>{market.question}</h1>
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
                <dd>{cents(lastPrice)}</dd>
              </div>
              <div>
                <dt>24h volume</dt>
                <dd>{dollars(market.volume24h)}</dd>
              </div>
              <div>
                <dt>Liquidity</dt>
                <dd>{dollars(market.liquidity)}</dd>
              </div>
              <div>
                <dt>Ends</dt>
                <dd>{market.endDate ? new Date(market.endDate).toLocaleDateString() : "–"}</dd>
              </div>
            </dl>
            <div className="chart-head">
              <span className="muted">{market.outcomes[outcome]} price</span>
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
