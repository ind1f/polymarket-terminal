import type { RankingChart, RankingColumn, RankingRow } from "./api";
import { shares } from "./format";

export type RankingEvent = { chart: string; rank: number | null; prefixMatch: boolean };

function targetRank(title: string): number | null {
  const numbered = title.match(/#(\d+)/);
  if (numbered) return Number(numbered[1]);
  return /\btop\b/i.test(title) ? 1 : null;
}

export function parseRankingEvent(title: string): RankingEvent | null {
  const appStore = title.match(/\b(free|paid)\b.*app store/i);
  if (appStore) {
    return { chart: `appstore-${appStore[1].toLowerCase()}`, rank: targetRank(title), prefixMatch: true };
  }
  const netflix = title.match(/\b(global|us) netflix (show|movie)/i);
  if (netflix) {
    const region = netflix[1].toLowerCase();
    const kind = netflix[2].toLowerCase() === "show" ? "tv" : "films";
    return { chart: `netflix-${region}-${kind}`, rank: targetRank(title), prefixMatch: false };
  }
  if (/steam weekly #\d+ seller/i.test(title)) {
    return { chart: "steam-weekly", rank: targetRank(title), prefixMatch: false };
  }
  return null;
}

function normalize(name: string): string {
  return name
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

export function findRow(
  rows: RankingRow[],
  label: string,
  prefixMatch: boolean,
): RankingRow | undefined {
  const target = normalize(label);
  if (target.length === 0) return undefined;
  const exact = rows.find((row) => normalize(row.name) === target);
  if (exact || !prefixMatch || target.length < 4) return exact;
  return rows.find((row) => {
    const name = normalize(row.name);
    return name.startsWith(target) || target.startsWith(name);
  });
}

const WIDTHS: Record<RankingColumn["kind"], string> = {
  rating: "40px",
  count: "76px",
  rank: "40px",
};

function formatValue(kind: RankingColumn["kind"], value: number | null): string {
  if (value === null) return "–";
  if (kind === "rating") return value.toFixed(1);
  if (kind === "count") return shares(value);
  return String(value);
}

type Props = {
  chart: RankingChart | null;
  error: string | null;
  labels: string[];
  ranking: RankingEvent;
};

export function RankingPanel({ chart, error, labels, ranking }: Props) {
  const traded = new Set(
    chart
      ? labels.map((label) => findRow(chart.rows, label, ranking.prefixMatch)).filter(Boolean)
      : [],
  );
  const columns = `30px minmax(0, 1fr) ${chart?.columns.map((column) => WIDTHS[column.kind]).join(" ") ?? ""}`;

  return (
    <section className="app-panel">
      <div className="app-panel-head">
        <span>{chart?.title ?? "Ranking"}</span>
        {chart && (
          <span className="muted">
            checked {new Date(chart.fetched_ms).toLocaleTimeString()}
          </span>
        )}
      </div>
      {chart?.period && <div className="app-panel-period muted">{chart.period}</div>}
      {!chart && <p className="message">{error ?? "Loading chart…"}</p>}
      {chart && (
        <div className="app-list">
          <div className="app-row app-row-head" style={{ gridTemplateColumns: columns }}>
            <span>#</span>
            <span>Name</span>
            {chart.columns.map((column) => (
              <span key={column.label}>{column.label}</span>
            ))}
          </div>
          {chart.rows.map((row) => (
            <div
              className={[
                "app-row",
                traded.has(row) ? "traded" : "",
                row.rank === ranking.rank ? "target" : "",
              ].join(" ")}
              key={`${row.rank}-${row.name}`}
              style={{ gridTemplateColumns: columns }}
            >
              <span>{row.rank}</span>
              <span title={row.name}>{row.name}</span>
              {chart.columns.map((column, index) => (
                <span key={column.label}>{formatValue(column.kind, row.values[index])}</span>
              ))}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
