const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const whole = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export function cents(price: number | null): string {
  return price === null ? "–" : `${(price * 100).toFixed(1)}¢`;
}

export function dollars(value: number): string {
  return `$${compact.format(value)}`;
}

export function shares(value: number): string {
  return whole.format(value);
}
