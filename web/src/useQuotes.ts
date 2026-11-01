import { useEffect, useState } from "react";

export type Quote = { bid: number | null; ask: number | null };

export function useQuotes(tokens: string[]): Record<string, Quote> {
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const key = tokens.join(",");

  useEffect(() => {
    setQuotes({});
    if (key === "") return;

    const scheme = location.protocol === "https:" ? "wss" : "ws";
    let socket: WebSocket;
    let timer: ReturnType<typeof setTimeout>;
    let closed = false;
    let delay = 500;

    const connect = () => {
      socket = new WebSocket(`${scheme}://${location.host}/ws/quotes`);
      socket.onopen = () => socket.send(JSON.stringify(key.split(",")));
      socket.onmessage = (message) => {
        delay = 500;
        const update: { connected: boolean; quotes: Record<string, Quote> } = JSON.parse(
          message.data,
        );
        setQuotes((previous) =>
          update.connected ? { ...previous, ...update.quotes } : {},
        );
      };
      socket.onclose = () => {
        if (closed) return;
        setQuotes({});
        timer = setTimeout(connect, delay);
        delay = Math.min(delay * 2, 5_000);
      };
    };

    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      socket.close();
    };
  }, [key]);

  return quotes;
}
