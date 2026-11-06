import type { Interval } from "./api";

export type View = "top" | "watchlist" | "new" | "random";

const VIEWS: View[] = ["top", "watchlist", "new", "random"];
const INTERVALS: Interval[] = ["1d", "1w", "1m", "max"];

export type UrlState = {
  view: View;
  eventId: string | null;
  marketId: string | null;
  outcome: number;
  interval: Interval;
};

export function readUrlState(): UrlState {
  const params = new URLSearchParams(location.search);
  const view = params.get("view") as View;
  const interval = params.get("range") as Interval;
  const digits = (value: string | null) => (value && /^\d+$/.test(value) ? value : null);
  return {
    view: VIEWS.includes(view) ? view : "top",
    eventId: digits(params.get("event")),
    marketId: digits(params.get("market")),
    outcome: params.get("side") === "1" ? 1 : 0,
    interval: INTERVALS.includes(interval) ? interval : "1w",
  };
}

export function writeUrlState(state: UrlState): void {
  const params = new URLSearchParams();
  if (state.view !== "top") params.set("view", state.view);
  if (state.eventId) params.set("event", state.eventId);
  if (state.marketId) params.set("market", state.marketId);
  if (state.outcome === 1) params.set("side", "1");
  if (state.interval !== "1w") params.set("range", state.interval);
  const query = params.toString();
  const next = `${location.pathname}${query ? `?${query}` : ""}`;
  if (next !== `${location.pathname}${location.search}`) history.replaceState(null, "", next);
}
