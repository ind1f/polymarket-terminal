import { useEffect, useState } from "react";

type State<T> = { data: T | null; error: string | null };

export function usePolling<T>(
  load: (signal: AbortSignal) => Promise<T>,
  key: string | null,
  intervalMs: number,
  keepData = false,
): State<T> {
  const [state, setState] = useState<State<T>>({ data: null, error: null });

  useEffect(() => {
    if (!keepData) setState({ data: null, error: null });
    if (key === null) return;

    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        const data = await load(controller.signal);
        if (controller.signal.aborted) return;
        setState({ data, error: null });
      } catch (error) {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : "Request failed";
        setState((previous) => ({ data: previous.data, error: message }));
      }
      timer = setTimeout(tick, intervalMs);
    };

    tick();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [key, intervalMs]);

  return state;
}
