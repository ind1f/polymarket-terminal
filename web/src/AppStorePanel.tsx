import type { AppChart, AppChartEntry } from "./api";
import { shares } from "./format";

export function parseAppStoreEvent(title: string) {
  const match = title.match(/\b(free|paid)\b.*app store/i);
  if (!match) return null;
  const rank = title.match(/#(\d+)/);
  return {
    chart: match[1].toLowerCase() as "free" | "paid",
    rank: rank ? Number(rank[1]) : null,
  };
}

function normalize(name: string): string {
  return name
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

export function findApp(apps: AppChartEntry[], label: string): AppChartEntry | undefined {
  const target = normalize(label);
  if (target.length === 0) return undefined;
  return (
    apps.find((app) => normalize(app.name) === target) ??
    (target.length < 4
      ? undefined
      : apps.find((app) => {
          const name = normalize(app.name);
          return name.startsWith(target) || target.startsWith(name);
        }))
  );
}

type Props = {
  chart: AppChart | null;
  error: string | null;
  labels: string[];
  targetRank: number | null;
};

export function AppStorePanel({ chart, error, labels, targetRank }: Props) {
  const traded = new Set(
    chart ? labels.map((label) => findApp(chart.apps, label)?.id).filter(Boolean) : [],
  );

  return (
    <section className="app-panel">
      <div className="app-panel-head">
        <span>{chart?.title ?? "App Store chart"}</span>
        {chart && (
          <span className="muted">
            checked {new Date(chart.fetched_ms).toLocaleTimeString()}
          </span>
        )}
      </div>
      {!chart && <p className="message">{error ?? "Loading chart…"}</p>}
      {chart && (
        <div className="app-list">
          <div className="app-row app-row-head">
            <span>#</span>
            <span>App</span>
            <span>Rating</span>
            <span>Ratings</span>
          </div>
          {chart.apps.map((app) => (
            <div
              className={[
                "app-row",
                traded.has(app.id) ? "traded" : "",
                app.rank === targetRank ? "target" : "",
              ].join(" ")}
              key={app.id}
            >
              <span>{app.rank}</span>
              <span title={app.name}>{app.name}</span>
              <span>{app.rating === null ? "–" : app.rating.toFixed(1)}</span>
              <span>{app.ratings === null ? "–" : shares(app.ratings)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
