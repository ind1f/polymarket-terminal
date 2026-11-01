import { useState } from "react";

export type WatchedEvent = { id: string; title: string };

const STORAGE_KEY = "watchlist";

function load(): WatchedEvent[] {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(stored) ? stored : [];
  } catch {
    return [];
  }
}

export function useWatchlist() {
  const [entries, setEntries] = useState<WatchedEvent[]>(load);

  const save = (next: WatchedEvent[]) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    setEntries(next);
  };

  const toggle = (event: WatchedEvent) => {
    const watched = entries.some((entry) => entry.id === event.id);
    save(
      watched
        ? entries.filter((entry) => entry.id !== event.id)
        : [...entries, { id: event.id, title: event.title }],
    );
  };

  const move = (id: string, insertBefore: number) => {
    const from = entries.findIndex((entry) => entry.id === id);
    if (from === -1) return;
    const next = entries.filter((entry) => entry.id !== id);
    next.splice(from < insertBefore ? insertBefore - 1 : insertBefore, 0, entries[from]);
    save(next);
  };

  return { entries, toggle, move, has: (id: string) => entries.some((entry) => entry.id === id) };
}
