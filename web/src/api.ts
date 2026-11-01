export type Market = {
  id: string;
  question: string;
  outcomes: string[];
  tokens: string[];
  lastPrice: number | null;
  volume24h: number;
  liquidity: number;
  endDate: string | null;
};

export type Level = { price: number; size: number };

export type Book = {
  bids: Level[];
  asks: Level[];
  timestamp: number;
};

export type PricePoint = { time: number; value: number };

export type Interval = "1d" | "1w" | "1m" | "max";

const FIDELITY: Record<Interval, number> = { "1d": 5, "1w": 30, "1m": 60, max: 720 };

type RawMarket = {
  id: string;
  question: string;
  outcomes?: string;
  clobTokenIds?: string;
  lastTradePrice?: number;
  volume24hr?: number;
  liquidityNum?: number;
  endDate?: string;
  acceptingOrders?: boolean;
  enableOrderBook?: boolean;
};

type RawLevel = { price: string; size: string };

async function getJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

function toMarket(raw: RawMarket): Market {
  return {
    id: raw.id,
    question: raw.question,
    outcomes: JSON.parse(raw.outcomes ?? "[]"),
    tokens: JSON.parse(raw.clobTokenIds ?? "[]"),
    lastPrice: raw.lastTradePrice ?? null,
    volume24h: raw.volume24hr ?? 0,
    liquidity: raw.liquidityNum ?? 0,
    endDate: raw.endDate ?? null,
  };
}

function isTradable(market: RawMarket): boolean {
  return Boolean(market.acceptingOrders && market.enableOrderBook && market.clobTokenIds);
}

function toLevels(levels: RawLevel[]): Level[] {
  return levels.map((level) => ({ price: Number(level.price), size: Number(level.size) }));
}

export async function fetchMarkets(signal: AbortSignal): Promise<Market[]> {
  const params = new URLSearchParams({
    active: "true",
    closed: "false",
    limit: "100",
    order: "volume24hr",
    ascending: "false",
  });
  const raw = await getJson<RawMarket[]>(`/api/gamma/markets?${params}`, signal);
  return raw
    .filter(isTradable)
    .map(toMarket);
}

export async function fetchMarket(id: string, signal: AbortSignal): Promise<Market> {
  return toMarket(await getJson<RawMarket>(`/api/gamma/markets/${id}`, signal));
}

export async function searchMarkets(query: string, signal: AbortSignal): Promise<Market[]> {
  const params = new URLSearchParams({
    q: query,
    limit_per_type: "20",
    events_status: "active",
  });
  const raw = await getJson<{ events?: { markets?: RawMarket[] }[] }>(
    `/api/gamma/public-search?${params}`,
    signal,
  );
  return (raw.events ?? [])
    .flatMap((event) => event.markets ?? [])
    .filter(isTradable)
    .map(toMarket)
    .sort((a, b) => b.volume24h - a.volume24h)
    .slice(0, 100);
}

export async function fetchBook(token: string, signal: AbortSignal): Promise<Book> {
  const raw = await getJson<{
    bids: RawLevel[];
    asks: RawLevel[];
    timestamp: string;
  }>(`/api/clob/book?token_id=${token}`, signal);
  return {
    bids: toLevels(raw.bids).sort((a, b) => b.price - a.price),
    asks: toLevels(raw.asks).sort((a, b) => a.price - b.price),
    timestamp: Number(raw.timestamp),
  };
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
