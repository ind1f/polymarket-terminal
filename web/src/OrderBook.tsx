import type { Book, Level } from "./api";
import { cents, shares } from "./format";

const DEPTH = 12;

type Row = Level & { total: number };

function withTotals(levels: Level[]): Row[] {
  let total = 0;
  return levels.slice(0, DEPTH).map((level) => {
    total += level.size;
    return { ...level, total };
  });
}

function Rows({ rows, side, max }: { rows: Row[]; side: "bid" | "ask"; max: number }) {
  return rows.map((row) => (
    <div className="book-row" key={row.price}>
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

export function OrderBook({ book }: { book: Book }) {
  const bids = withTotals(book.bids);
  const asks = withTotals(book.asks);
  const max = Math.max(bids.at(-1)?.total ?? 0, asks.at(-1)?.total ?? 0, 1);
  const spread = book.bids[0] && book.asks[0] ? book.asks[0].price - book.bids[0].price : null;

  return (
    <div className="book">
      <div className="book-row book-head">
        <span>Price</span>
        <span>Size</span>
        <span>Total</span>
      </div>
      <div className="book-side-label">Asks</div>
      <div className="book-asks">
        <Rows rows={[...asks].reverse()} side="ask" max={max} />
      </div>
      <div className="book-spread">Spread {cents(spread)}</div>
      <div className="book-bids">
        <Rows rows={bids} side="bid" max={max} />
      </div>
      <div className="book-side-label">Bids</div>
    </div>
  );
}
