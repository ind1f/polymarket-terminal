export type Market = {
  id: string;
  label: string;
  outcomes: string[];
  tokens: string[];
  price: number | null;
  bestBid: number | null;
  bestAsk: number | null;
  lastPrice: number | null;
  volume24h: number;
  rules: string;
  resolutionSource: string | null;
  closed: boolean;
  result: number | null;
};

export type MarketEvent = {
  id: string;
  title: string;
  slug: string | null;
  seriesId: string | null;
  volume24h: number;
  liquidity: number;
  endDate: string | null;
  createdAt: string | null;
  rules: string;
  resolutionSource: string | null;
  markets: Market[];
};

export type Level = { price: number; size: number };

export type Book = {
  bids: Level[];
  asks: Level[];
  timestamp: number;
};

export type RankingColumn = { label: string; kind: "rating" | "count" | "rank" };

export type RankingRow = { rank: number; name: string; values: (number | null)[] };

export type RankingChart = {
  id: string;
  title: string;
  period: string | null;
  rank_label: string;
  columns: RankingColumn[];
  rows: RankingRow[];
  fetched_ms: number;
};

export type SeriesEvent = {
  id: string;
  title: string;
  end_date: string | null;
  closed: boolean;
  result: string | null;
};

export type Series = { key: string; events: SeriesEvent[]; fetched_ms: number };

export function placeholderEvent(
  id: string,
  title: string,
  extra: Partial<MarketEvent> = {},
): MarketEvent {
  return {
    id,
    title,
    slug: null,
    seriesId: null,
    volume24h: 0,
    liquidity: 0,
    endDate: null,
    createdAt: null,
    rules: "",
    resolutionSource: null,
    markets: [],
    ...extra,
  };
}

export async function fetchMarketHistory(eventId: string, signal: AbortSignal): Promise<Series> {
  return getJson<Series>(`/api/history/${eventId}`, signal);
}

export type PricePoint = { time: number; value: number };

export type Interval = "1d" | "1w" | "1m" | "max";

const EXCLUDED_TAG_IDS = ["102169", "101757", "100639"];
const RANDOM_BATCHES = 6;
const RANDOM_BATCH_SIZE = 5;
const RANDOM_MAX_OFFSET = 2000;

const FIDELITY: Record<Interval, number> = { "1d": 5, "1w": 30, "1m": 60, max: 720 };

type RawMarket = {
  id: string;
  question: string;
  groupItemTitle?: string;
  outcomes?: string;
  outcomePrices?: string;
  clobTokenIds?: string;
  bestBid?: number;
  bestAsk?: number;
  lastTradePrice?: number;
  volume24hr?: number;
  acceptingOrders?: boolean;
  enableOrderBook?: boolean;
  active?: boolean;
  closed?: boolean;
  description?: string;
  resolutionSource?: string;
};

type RawEvent = {
  id: string;
  title: string;
  slug?: string;
  series?: { id: string }[];
  volume24hr?: number;
  liquidity?: number;
  endDate?: string;
  createdAt?: string;
  description?: string;
  resolutionSource?: string;
  markets?: RawMarket[];
};

class HttpError extends Error {
  constructor(readonly status: number) {
    super(`Request failed: ${status}`);
  }
}

async function getJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new HttpError(response.status);
  return response.json() as Promise<T>;
}

function toMarket(raw: RawMarket): Market {
  const prices: string[] = JSON.parse(raw.outcomePrices ?? "[]");
  const settled = prices.map(Number);
  const resolved = Boolean(raw.closed) && settled.length === 2 && settled.includes(1);
  return {
    id: raw.id,
    label: raw.groupItemTitle || raw.question,
    outcomes: JSON.parse(raw.outcomes ?? "[]"),
    tokens: JSON.parse(raw.clobTokenIds ?? "[]"),
    price: prices[0] ? Number(prices[0]) : null,
    bestBid: raw.bestBid ?? null,
    bestAsk: raw.bestAsk ?? null,
    lastPrice: raw.lastTradePrice ?? null,
    volume24h: raw.volume24hr ?? 0,
    rules: raw.description?.trim() ?? "",
    resolutionSource: raw.resolutionSource?.trim() || null,
    closed: !raw.acceptingOrders,
    result: resolved ? settled.indexOf(1) : null,
  };
}

function toEvent(raw: RawEvent): MarketEvent {
  return {
    id: raw.id,
    title: raw.title,
    slug: raw.slug ?? null,
    seriesId: raw.series?.[0]?.id ?? null,
    volume24h: raw.volume24hr ?? 0,
    liquidity: raw.liquidity ?? 0,
    endDate: raw.endDate ?? null,
    createdAt: raw.createdAt ?? null,
    rules: raw.description?.trim() ?? "",
    resolutionSource: raw.resolutionSource?.trim() || null,
    markets: listedMarkets(raw.markets ?? []).sort((a, b) => (b.price ?? 0) - (a.price ?? 0)),
  };
}

function listedMarkets(raw: RawMarket[]): Market[] {
  const open = raw.filter(isTradable).map(toMarket);
  if (open.length > 0) return open;
  return raw
    .filter((market) => market.closed && market.clobTokenIds)
    .map((market) => ({ raw: market, parsed: toMarket(market) }))
    .filter(({ raw: market, parsed }) => market.active !== false || parsed.result === 0)
    .map(({ parsed }) => parsed);
}

export function eventResult(event: MarketEvent): string | null {
  if (event.markets.length === 0 || event.markets.some((market) => !market.closed)) return null;
  if (event.markets.length === 1) {
    const [market] = event.markets;
    return market.result === null ? "Awaiting resolution" : market.outcomes[market.result];
  }
  if (event.markets.some((market) => market.result === null)) return "Awaiting resolution";
  return event.markets.find((market) => market.result === 0)?.label ?? "None of the listed outcomes";
}

function isTradable(market: RawMarket): boolean {
  return Boolean(market.acceptingOrders && market.enableOrderBook && market.clobTokenIds);
}

export async function fetchEvents(signal: AbortSignal): Promise<MarketEvent[]> {
  const params = new URLSearchParams({
    active: "true",
    closed: "false",
    limit: "100",
    order: "volume24hr",
    ascending: "false",
  });
  const raw = await getJson<RawEvent[]>(`/api/gamma/events?${params}`, signal);
  return raw.map(toEvent).filter((event) => event.markets.length > 0);
}

function discoveryParams(values: Record<string, string>): URLSearchParams {
  const params = new URLSearchParams({ active: "true", closed: "false", ...values });
  for (const id of EXCLUDED_TAG_IDS) params.append("exclude_tag_id", id);
  return params;
}

export async function fetchNewEvents(signal: AbortSignal): Promise<MarketEvent[]> {
  const params = discoveryParams({ limit: "50", order: "createdAt", ascending: "false" });
  const raw = await getJson<RawEvent[]>(`/api/gamma/events?${params}`, signal);
  return raw.map(toEvent).filter((event) => event.markets.length > 0);
}

export async function fetchRandomEvents(signal: AbortSignal): Promise<MarketEvent[]> {
  const batches = await Promise.all(
    Array.from({ length: RANDOM_BATCHES }, () => {
      const params = discoveryParams({
        limit: String(RANDOM_BATCH_SIZE),
        offset: String(Math.floor(Math.random() * RANDOM_MAX_OFFSET)),
        order: "createdAt",
        ascending: String(Math.random() < 0.5),
      });
      return getJson<RawEvent[]>(`/api/gamma/events?${params}`, signal);
    }),
  );
  const unique = new Map(batches.flat().map((event) => [event.id, event]));
  return [...unique.values()]
    .map(toEvent)
    .filter((event) => event.markets.length > 0)
    .map((event) => ({ event, order: Math.random() }))
    .sort((a, b) => a.order - b.order)
    .map(({ event }) => event);
}

export async function fetchEvent(id: string, signal: AbortSignal): Promise<MarketEvent> {
  return toEvent(await getJson<RawEvent>(`/api/gamma/events/${id}`, signal));
}

export async function fetchWatchedEvents(
  entries: { id: string; title: string }[],
  signal: AbortSignal,
): Promise<MarketEvent[]> {
  return Promise.all(
    entries.map((entry) =>
      fetchEvent(entry.id, signal).catch((error) => {
        if (error instanceof HttpError && error.status === 404) {
          return toEvent({ id: entry.id, title: entry.title });
        }
        throw error;
      }),
    ),
  );
}

export async function searchEvents(query: string, signal: AbortSignal): Promise<MarketEvent[]> {
  const params = new URLSearchParams({
    q: query,
    limit_per_type: "20",
    events_status: "active",
  });
  const raw = await getJson<{ events?: RawEvent[] }>(`/api/gamma/public-search?${params}`, signal);
  return (raw.events ?? [])
    .map(toEvent)
    .filter((event) => event.markets.length > 0)
    .sort((a, b) => b.volume24h - a.volume24h);
}

export async function fetchRanking(chart: string, signal: AbortSignal): Promise<RankingChart> {
  return getJson<RankingChart>(`/api/rankings/${chart}`, signal);
}

export async function fetchHistory(
  token: string,
  interval: Interval,
  signal: AbortSignal,
): Promise<PricePoint[]> {
  const params = new URLSearchParams({
    market: token,
    interval,
    fidelity: String(FIDELITY[interval]),
  });
  const raw = await getJson<{ history: { t: number; p: number }[] }>(
    `/api/clob/prices-history?${params}`,
    signal,
  );
  const sorted = [...raw.history].sort((a, b) => a.t - b.t);
  return sorted
    .filter((point, index) => index === 0 || point.t > sorted[index - 1].t)
    .map((point) => ({ time: point.t, value: point.p }));
}
