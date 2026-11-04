import { useEffect, useState, type DragEvent } from "react";
import { GiftIcon } from "./GiftIcon";
import {
  eventResult,
  eventRewards,
  rewardSummary,
  fetchEvent,
  fetchEvents,
  fetchHistory,
  fetchNewEvents,
  fetchRandomEvents,
  fetchRanking,
  fetchMarketHistory,
  fetchWatchedEvents,
  placeholderEvent,
  searchEvents,
  type Interval,
  type Market,
  type MarketEvent,
} from "./api";
import { age, cents, dollars } from "./format";
import { OrderBook } from "./OrderBook";
import { PriceChart } from "./PriceChart";
import { findRow, parseRankingEvent, RankingPanel } from "./RankingPanel";
import { Rules } from "./Rules";
import { SeriesPicker } from "./SeriesPicker";
import { Splitter } from "./Splitter";
import { useBook } from "./useBook";
import { usePanelWidths } from "./usePanelWidths";
import { usePolling } from "./usePolling";
import { useQuotes, type Quote } from "./useQuotes";
import { useWatchlist } from "./useWatchlist";

const INTERVALS: Interval[] = ["1d", "1w", "1m", "max"];

type View = "top" | "watchlist" | "new" | "random";

const VIEWS: { id: View; label: string }[] = [
  { id: "top", label: "Top" },
  { id: "watchlist", label: "Watchlist" },
  { id: "new", label: "New" },
  { id: "random", label: "Random" },
];

function flip(price: number | null): number | null {
  return price === null ? null : 1 - price;
}

function quote(market: Market, outcome: number, live?: Quote) {
  const bid = live ? live.bid : market.bestBid;
  const ask = live ? live.ask : market.bestAsk;
  if (outcome === 0) return { price: market.price, bid, ask, last: market.lastPrice };
  return {
    price: flip(market.price),
    bid: flip(ask),
    ask: flip(bid),
    last: flip(market.lastPrice),
  };
}

function topLine(event: MarketEvent, loading: boolean): string {
  const top = event.markets[0];
  if (!top) return loading ? "Loading…" : "No open markets";
  const result = eventResult(event);
  if (result) return result === "Awaiting resolution" ? "Closed, awaiting result" : `Result: ${result}`;
  return event.markets.length > 1 ? `${top.label} ${cents(top.price)}` : cents(top.price);
}

export function App() {
  const events = usePolling(fetchEvents, "events", 300_000);
  const watchlist = useWatchlist();
  const panels = usePanelWidths();
  const [view, setView] = useState<View>("top");
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [dropIndex, setDropIndex] = useState<number | null>(null);
  const [shuffles, setShuffles] = useState(0);
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
  const watchedKey = watchlist.entries.map((entry) => entry.id).join(",");
  const watched = usePolling(
    (signal) => fetchWatchedEvents(watchlist.entries, signal),
    view === "watchlist" && watchedKey ? watchedKey : null,
    30_000,
    true,
  );
  const watchedRows = {
    data: watchlist.entries.map(
      (entry) =>
        watched.data?.find((candidate) => candidate.id === entry.id) ??
        placeholderEvent(entry.id, entry.title),
    ),
    error: watched.error,
  };
  const newEvents = usePolling(fetchNewEvents, view === "new" ? "new" : null, 120_000);
  const randomEvents = usePolling(
    fetchRandomEvents,
    view === "random" ? `random-${shuffles}` : null,
    null,
  );
  const views = { top: events, watchlist: watchedRows, new: newEvents, random: randomEvents };
  const list = query ? results : views[view];
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
  const closed = market?.closed ?? false;
  const result = event ? eventResult(event) : null;
  const series = usePolling(
    (signal) => fetchMarketHistory(event!.id, signal),
    event?.seriesId ? event.id : null,
    300_000,
    true,
  );

  const book = useBook(closed ? null : token);
  const quotes = useQuotes(
    event && event.markets.length > 1
      ? event.markets.filter((candidate) => !candidate.closed).map((candidate) => candidate.tokens[0])
      : [],
  );
  const historyKey = token && `${token}:${interval}`;
  const history = usePolling(
    (signal) => fetchHistory(token!, interval, signal),
    historyKey,
    60_000,
  );

  const ranking = event ? parseRankingEvent(event.title) : null;
  const rankChart = usePolling(
    (signal) => fetchRanking(ranking!.chart, signal),
    ranking?.chart ?? null,
    60_000,
  );
  const rankColumn = rankChart.data !== null && ranking !== null && result === null;

  const selectEvent = (next: MarketEvent) => {
    setSelected(next);
    setMarketId(next.markets[0]?.id ?? null);
    setOutcome(0);
  };

  const selectMarket = (next: Market) => {
    setSelected(event);
    setMarketId(next.id);
  };

  const reorderable = view === "watchlist" && !search;

  const trackDrop = (dragEvent: DragEvent<HTMLDivElement>, index: number) => {
    if (draggedId === null) return;
    dragEvent.preventDefault();
    const { top, height } = dragEvent.currentTarget.getBoundingClientRect();
    setDropIndex(dragEvent.clientY < top + height / 2 ? index : index + 1);
  };

  const finishDrag = () => {
    setDraggedId(null);
    setDropIndex(null);
  };

  const selectView = (next: View) => {
    setView(next);
    setSearch("");
    setQuery("");
  };

  const bestBid = book.data?.bids[0]?.price ?? null;
  const bestAsk = book.data?.asks[0]?.price ?? null;

  return (
    <div
      className="app"
      style={{
        gridTemplateColumns: `${panels.widths.left}px minmax(0, 1fr) ${panels.widths.right}px`,
      }}
    >
      <header className="topbar">
        <strong>Polymarket Terminal</strong>
        <span className="badge">Read-only</span>
        <span className="muted topbar-status">
          {book.error
            ? book.error
            : book.data && `Live, last change ${new Date(book.data.timestamp).toLocaleTimeString()}`}
        </span>
      </header>

      <aside className="panel markets">
        <Splitter
          side="left"
          width={panels.widths.left}
          label="Resize market list"
          onResize={panels.resize}
        />
        <div className="tabs view-tabs" role="group" aria-label="Market list">
          {VIEWS.map(({ id, label }) => (
            <button
              key={id}
              className={id === view && !search ? "active" : ""}
              onClick={() => selectView(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <input
          className="search"
          type="search"
          placeholder="Search all markets"
          aria-label="Search markets"
          value={search}
          onChange={(change) => setSearch(change.target.value)}
        />
        {view === "random" && !search && (
          <button className="shuffle" onClick={() => setShuffles(shuffles + 1)}>
            Shuffle
          </button>
        )}
        <div className="market-list">
          {list.error && !list.data && (
            <p className="message">Couldn't load markets: {list.error}</p>
          )}
          {!list.data && !list.error && <p className="message">Loading markets…</p>}
          {list.data?.length === 0 && (
            <p className="message">
              {view === "watchlist" && !query ? "Star a market to add it here" : "No matches"}
            </p>
          )}
          {list.data?.map((candidate, index) => {
            const starred = watchlist.has(candidate.id);
            const dropAbove = dropIndex === index;
            const dropBelow = dropIndex === index + 1 && index === list.data!.length - 1;
            return (
              <div
                className={[
                  "market-row",
                  candidate.id === event?.id ? "active" : "",
                  reorderable ? "reorderable" : "",
                  candidate.id === draggedId ? "dragging" : "",
                  dropAbove ? "drop-above" : "",
                  dropBelow ? "drop-below" : "",
                ].join(" ")}
                key={candidate.id}
                draggable={reorderable}
                onDragStart={(dragEvent) => {
                  dragEvent.dataTransfer.effectAllowed = "move";
                  dragEvent.dataTransfer.setData("text/plain", candidate.title);
                  setDraggedId(candidate.id);
                }}
                onDragOver={(dragEvent) => trackDrop(dragEvent, index)}
                onDrop={(dragEvent) => {
                  dragEvent.preventDefault();
                  if (draggedId !== null && dropIndex !== null) {
                    watchlist.move(draggedId, dropIndex);
                  }
                  finishDrag();
                }}
                onDragEnd={finishDrag}
                onKeyDown={(keyEvent) => {
                  if (!reorderable || !keyEvent.altKey) return;
                  if (keyEvent.key !== "ArrowUp" && keyEvent.key !== "ArrowDown") return;
                  keyEvent.preventDefault();
                  const target = keyEvent.key === "ArrowUp" ? index - 1 : index + 2;
                  if (target >= 0 && target <= list.data!.length) {
                    watchlist.move(candidate.id, target);
                  }
                }}
              >
                <button className="market-open" onClick={() => selectEvent(candidate)}>
                  <span className="market-question">{candidate.title}</span>
                  <span className="market-meta">
                    <span className="market-top">
                      {topLine(candidate, !watched.data?.some(({ id }) => id === candidate.id))}
                    </span>
                    <span className="muted market-volume">
                      {eventRewards(candidate) && (
                        <GiftIcon
                          title={`Liquidity rewards: $${eventRewards(candidate)!.dailyRate}/day across ${eventRewards(candidate)!.outcomes} outcome${eventRewards(candidate)!.outcomes === 1 ? "" : "s"}`}
                        />
                      )}
                      {view === "new" && !search && candidate.createdAt
                        ? age(candidate.createdAt)
                        : `${dollars(candidate.volume24h)} 24h`}
                    </span>
                  </span>
                </button>
                <button
                  className={`star ${starred ? "on" : ""}`}
                  aria-label={starred ? "Remove from watchlist" : "Add to watchlist"}
                  aria-pressed={starred}
                  onClick={() => watchlist.toggle(candidate)}
                >
                  {starred ? "★" : "☆"}
                </button>
              </div>
            );
          })}
        </div>
      </aside>

      <main className="panel detail">
        {event && market ? (
          <>
            <div className="detail-title">
              <h1>{event.title}</h1>
              <button
                className={`star ${watchlist.has(event.id) ? "on" : ""}`}
                aria-label={watchlist.has(event.id) ? "Remove from watchlist" : "Add to watchlist"}
                aria-pressed={watchlist.has(event.id)}
                onClick={() => watchlist.toggle(event)}
              >
                {watchlist.has(event.id) ? "★" : "☆"}
              </button>
            </div>
            <div className="detail-meta">
              {event.seriesId && series.data?.events.some((item) => item.id === event.id) && (
                <SeriesPicker
                  series={series.data}
                  selectedId={event.id}
                  selectedTitle={event.title}
                  onSelect={(picked) =>
                    selectEvent(
                      placeholderEvent(picked.id, picked.title, {
                        seriesId: event.seriesId,
                        endDate: picked.end_date,
                      }),
                    )
                  }
                />
              )}
              {event.slug && (
                <a
                  className="external"
                  href={`https://polymarket.com/event/${encodeURIComponent(event.slug)}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Polymarket ↗
                </a>
              )}
            </div>
            <div className="stats-row">
              <dl className="stats">
                {result ? (
                  <div>
                    <dt>Result</dt>
                    <dd>{result}</dd>
                  </div>
                ) : (
                  <>
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
                    {eventRewards(event) && (
                      <div title={market.rewards ? rewardSummary(market.rewards) : "No rewards on this outcome"}>
                        <dt>Rewards</dt>
                        <dd>{market.rewards ? `$${market.rewards.dailyRate}/day` : "–"}</dd>
                      </div>
                    )}
                  </>
                )}
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
                <div className={`outcome-row outcome-head ${rankColumn ? "with-rank" : ""}`}>
                  <span>Outcome</span>
                  {rankColumn && <span>{rankChart.data!.rank_label}</span>}
                  <span>{market.outcomes[outcome]}</span>
                  <span>Bid</span>
                  <span>Ask</span>
                  <span>24h</span>
                </div>
                {event.markets.map((candidate) => {
                  const active = candidate.id === market.id;
                  const row = quote(candidate, outcome, quotes[candidate.tokens[0]]);
                  const won = candidate.result === 0;
                  return (
                    <button
                      className={`outcome-row ${active ? "active" : ""} ${rankColumn ? "with-rank" : ""} ${won ? "won" : ""}`}
                      key={candidate.id}
                      onClick={() => selectMarket(candidate)}
                    >
                      <span>
                        {won ? `✓ ${candidate.label}` : candidate.label}
                        {candidate.rewards && <GiftIcon title={rewardSummary(candidate.rewards)} />}
                      </span>
                      {rankColumn && (
                        <span>
                          {findRow(rankChart.data!.rows, candidate.label, ranking!.prefixMatch)
                            ?.rank ?? "–"}
                        </span>
                      )}
                      <span>{cents(row.price)}</span>
                      <span>
                        {candidate.closed ? "–" : cents(active && book.data ? bestBid : row.bid)}
                      </span>
                      <span>
                        {candidate.closed ? "–" : cents(active && book.data ? bestAsk : row.ask)}
                      </span>
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
            <div className="chart-row">
              <div className="chart-wrap">
                <PriceChart points={history.data ?? []} resetKey={historyKey ?? ""} />
                {history.error && !history.data && (
                  <p className="message overlay">Couldn't load history: {history.error}</p>
                )}
                {history.data?.length === 0 && (
                  <p className="message overlay">
                    No price history for this range
                    {closed && interval !== "max" && (
                      <>
                        {" · "}
                        <button className="inline-action" onClick={() => setInterval("max")}>
                          Show full history
                        </button>
                      </>
                    )}
                  </p>
                )}
              </div>
              {ranking && (
                <RankingPanel
                  chart={rankChart.data}
                  error={rankChart.error}
                  labels={event.markets.map((candidate) => candidate.label)}
                  ranking={ranking}
                />
              )}
            </div>
            <Rules
              text={market.rules || event.rules}
              source={market.resolutionSource ?? event.resolutionSource}
            />
          </>
        ) : (
          <p className="message">
            {!event
              ? "Select a market"
              : live.data?.id === event.id
                ? "No markets to show in this event"
                : "Loading market…"}
          </p>
        )}
      </main>

      <aside className="panel book-panel">
        <Splitter
          side="right"
          width={panels.widths.right}
          label="Resize order book"
          onResize={panels.resize}
        />
        <h2>Order book</h2>
        {closed && <p className="message">Market closed, so there is no order book.</p>}
        {!closed && book.error && !book.data && <p className="message">{book.error}</p>}
        {!closed && !book.data && !book.error && <p className="message">Loading book…</p>}
        {book.data && <OrderBook book={book.data} rewards={closed ? null : (market?.rewards ?? null)} />}
      </aside>
    </div>
  );
}
