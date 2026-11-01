import { useEffect, useState } from "react";
import type { Book } from "./api";

type State = { data: Book | null; error: string | null };

const OFFLINE = "Live feed offline";
const RECONNECTING = "Reconnecting to Polymarket";

export function useBook(token: string | null): State {
  const [state, setState] = useState<State>({ data: null, error: null });

  useEffect(() => {
    setState({ data: null, error: null });
    if (token === null) return;

    const scheme = location.protocol === "https:" ? "wss" : "ws";
    let socket: WebSocket;
    let timer: ReturnType<typeof setTimeout>;
    let closed = false;
    let delay = 500;

    const connect = () => {
      socket = new WebSocket(`${scheme}://${location.host}/ws/book/${token}`);
      socket.onmessage = (message) => {
        delay = 500;
        const update: { connected: boolean; book: Book | null } = JSON.parse(message.data);
        setState((previous) => ({
          data: update.book ?? previous.data,
          error: update.connected ? null : RECONNECTING,
        }));
      };
      socket.onclose = () => {
        if (closed) return;
        setState((previous) => ({ data: previous.data, error: OFFLINE }));
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
  }, [token]);

  return state;
}
