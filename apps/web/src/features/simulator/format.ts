/* Locale-aware display formatters for simulator values.
 *
 * Formatting only — no arithmetic. Money arrives from the API as Decimal
 * strings, counts as floats, and rates as Decimal fractions.
 */

export function formatCount(locale: string, value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "-";
  try {
    return new Intl.NumberFormat(locale).format(Number(value));
  } catch {
    return String(value);
  }
}

export function formatPercent(
  locale: string,
  value: string | number | null | undefined
): string {
  if (value === null || value === undefined || value === "") return "-";
  const amount = Number(typeof value === "string" ? value.replace(/[^0-9.-]/g, "") : value);
  if (Number.isNaN(amount)) return "-";
  try {
    return new Intl.NumberFormat(locale, {
      style: "percent",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${(amount * 100).toFixed(2)}%`;
  }
}

export function formatMultiplier(
  locale: string,
  value: string | number | null | undefined
): string {
  if (value === null || value === undefined || value === "") return "-";
  const amount = Number(typeof value === "string" ? value.replace(/[^0-9.-]/g, "") : value);
  if (Number.isNaN(amount)) return "-";
  try {
    return `${new Intl.NumberFormat(locale, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount)}×`;
  } catch {
    return `${amount.toFixed(2)}×`;
  }
}

export function formatDateTime(locale: string, value: string | null | undefined): string {
  if (!value) return "-";
  try {
    return new Intl.DateTimeFormat(locale, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

export function formatDate(locale: string, value: string | null | undefined): string {
  if (!value) return "-";
  try {
    return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(value));
  } catch {
    return value;
  }
}