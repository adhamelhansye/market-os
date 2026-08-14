/* Money display helpers.
 *
 * The API serializes every money field as a string (backend Decimals with
 * json_encoders). Display formatting goes through Intl.NumberFormat; we
 * never perform arithmetic on money values in the client.
 */

export function parseMoney(value: string | null | undefined): number {
  if (value === null || value === undefined || value === "") return 0;
  const cleaned = value.replace(/[^0-9.-]/g, "");
  return Number(cleaned);
}

export function formatMoney(
  value: string | null | undefined,
  currency: string,
  locale: string,
  options: { decimals?: number } = {}
): string {
  const amount = parseMoney(value);
  const decimals = options.decimals ?? 2;
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(amount);
  } catch {
    return `${amount.toFixed(decimals)} ${currency}`;
  }
}

export function formatRatio(
  value: string | null | undefined,
  locale: string
): string | null {
  if (value === null || value === undefined || value === "") return null;
  const amount = parseMoney(value);
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