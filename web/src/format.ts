const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const whole = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export function cents(price: number | null): string {
  return price === null ? "–" : `${(price * 100).toFixed(1)}¢`;
}

export function dollars(value: number): string {
  return `$${compact.format(value)}`;
}

export function age(timestamp: string): string {
  const minutes = Math.max(0, Math.floor((Date.now() - Date.parse(timestamp)) / 60_000));
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`;
  return `${Math.floor(minutes / 1440)}d ago`;
}

export function shares(value: number): string {
  return whole.format(value);
}
