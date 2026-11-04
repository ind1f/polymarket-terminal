import type { Book, Level, Rewards } from "./api";
import { cents, shares } from "./format";

type Band = { low: number; high: number };

const DEPTH = 12;

type Row = Level & { total: number };

function withTotals(levels: Level[]): Row[] {
  let total = 0;
  return levels.slice(0, DEPTH).map((level) => {
    total += level.size;
    return { ...level, total };
  });
}

type RowsProps = { rows: Row[]; side: "bid" | "ask"; max: number; band: Band | null };

function inBand(price: number, band: Band | null): boolean {
  return band !== null && price >= band.low - 1e-9 && price <= band.high + 1e-9;
}

function Rows({ rows, side, max, band }: RowsProps) {
  return rows.map((row) => (
    <div className={`book-row ${inBand(row.price, band) ? "in-band" : ""}`} key={row.price}>
      <span
        className={`book-bar ${side}`}
        style={{ width: `${(row.total / max) * 100}%` }}
      />
      <span>{cents(row.price)}</span>
      <span>{shares(row.size)}</span>
      <span>{shares(row.total)}</span>
    </div>
  ));
}

export function OrderBook({ book, rewards }: { book: Book; rewards: Rewards | null }) {
  const bids = withTotals(book.bids);
  const asks = withTotals(book.asks);
  const max = Math.max(bids.at(-1)?.total ?? 0, asks.at(-1)?.total ?? 0, 1);
  const spread = book.bids[0] && book.asks[0] ? book.asks[0].price - book.bids[0].price : null;
  const mid = book.bids[0] && book.asks[0] ? (book.bids[0].price + book.asks[0].price) / 2 : null;
  const band =
    rewards?.maxSpread != null && mid !== null
      ? { low: mid - rewards.maxSpread / 100, high: mid + rewards.maxSpread / 100 }
      : null;

  return (
    <div className="book">
      {rewards && (
        <div className="book-rewards">
          {band
            ? `Rewards zone ${cents(Math.max(band.low, 0))}–${cents(Math.min(band.high, 1))}`
            : "Rewards zone needs both a bid and an ask"}
          {rewards.minSize != null && ` · min ${rewards.minSize} shares`} · ${rewards.dailyRate}/day
        </div>
      )}
      <div className="book-row book-head">
        <span>Price</span>
        <span>Size</span>
        <span>Total</span>
      </div>
      <div className="book-side-label">Asks</div>
      <div className="book-asks">
        <Rows rows={[...asks].reverse()} side="ask" max={max} band={band} />
      </div>
      <div className="book-spread">Spread {cents(spread)}</div>
      <div className="book-bids">
        <Rows rows={bids} side="bid" max={max} band={band} />
      </div>
      <div className="book-side-label">Bids</div>
    </div>
  );
}
