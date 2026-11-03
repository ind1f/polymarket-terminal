import type { Series, SeriesEvent } from "./api";

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];
const MONTH = MONTHS.join("|");
const DAY_DATE = new RegExp(`\\b(${MONTH}) (\\d{1,2})(?:\\s*-\\s*(?:(${MONTH}) )?(\\d{1,2}))?\\b`);
const MONTH_ONLY = new RegExp(`\\b(${MONTH})\\b`);

type Dated = SeriesEvent & { label: string; sortKey: number; template: string };

function easternYearMonth(iso: string | null): { year: number; month: number } | null {
  if (!iso) return null;
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "numeric",
  }).formatToParts(new Date(iso));
  const value = (type: string) => Number(parts.find((part) => part.type === type)?.value);
  return { year: value("year"), month: value("month") - 1 };
}

function shape(title: string, phrase: string): string {
  return title.replace(phrase, "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

function short(month: string): string {
  return month.slice(0, 3);
}

function yearFor(month: number, end: { year: number; month: number } | null): number | null {
  if (!end) return null;
  if (month === 0 && end.month === 11) return end.year + 1;
  if (month === 11 && end.month === 0) return end.year - 1;
  return end.year;
}

function date(item: SeriesEvent): Dated {
  const end = easternYearMonth(item.end_date);
  const fallbackKey = item.end_date ? Date.parse(item.end_date) : 0;
  const day = item.title.match(DAY_DATE);
  if (day) {
    const [phrase, startMonth, startDay, rangeMonth, rangeDay] = day;
    const lastMonth = MONTHS.indexOf(rangeMonth ?? startMonth);
    const year = yearFor(lastMonth, end);
    const range = rangeDay ? ` – ${short(rangeMonth ?? startMonth)} ${rangeDay}` : "";
    return {
      ...item,
      label: `${short(startMonth)} ${startDay}${range}${year ? `, ${year}` : ""}`,
      sortKey: year ? Date.UTC(year, lastMonth, Number(rangeDay ?? startDay)) : fallbackKey,
      template: shape(item.title, phrase),
    };
  }
  const month = item.title.match(MONTH_ONLY);
  if (month) {
    const index = MONTHS.indexOf(month[1]);
    const year = yearFor(index, end);
    return {
      ...item,
      label: `${month[1]}${year ? ` ${year}` : ""}`,
      sortKey: year ? Date.UTC(year, index, 1) : fallbackKey,
      template: shape(item.title, month[1]),
    };
  }
  return {
    ...item,
    label: item.end_date
      ? new Date(item.end_date).toLocaleDateString("en-US", {
          timeZone: "America/New_York",
          month: "short",
          day: "numeric",
          year: "numeric",
        })
      : item.title,
    sortKey: fallbackKey,
    template: shape(item.title, ""),
  };
}

type Props = {
  series: Series;
  selectedId: string;
  selectedTitle: string;
  onSelect: (item: SeriesEvent) => void;
};

export function SeriesPicker({ series, selectedId, selectedTitle, onSelect }: Props) {
  const template = date({ id: "", title: selectedTitle, end_date: null, closed: false, result: null }).template;
  const all = series.events.map(date);
  const matching = all.filter((item) => item.template === template);
  const items = (matching.length > 0 ? matching : all).sort((a, b) => b.sortKey - a.sortKey);
  const now = Date.now();
  const ended = (item: Dated) => item.end_date !== null && Date.parse(item.end_date) < now;
  const currentId = items.filter((item) => !item.closed && !ended(item)).at(-1)?.id;
  const status = (item: Dated) => {
    if (item.closed) return item.result ?? "awaiting result";
    if (ended(item)) return "awaiting result";
    return item.id === currentId ? "current" : "upcoming";
  };
  if (items.length < 2 && items[0]?.id === selectedId) return null;

  return (
    <select
      className="series-picker"
      aria-label="Market date"
      value={selectedId}
      onChange={(change) => {
        const picked = items.find((item) => item.id === change.target.value);
        if (picked) onSelect(picked);
      }}
    >
      {!items.some((item) => item.id === selectedId) && (
        <option value={selectedId}>This market</option>
      )}
      {items.map((item) => (
        <option key={item.id} value={item.id}>
          {item.label} · {status(item)}
        </option>
      ))}
    </select>
  );
}
