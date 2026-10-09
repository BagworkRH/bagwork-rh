/**
 * Money display formatting.
 *
 * The API returns 18-decimal strings because the ledger runs in token units, so
 * an unformatted figure looks like "575.000000000000000000" — which reads as a
 * bug. Every amount the UI prints goes through here, so the number of decimal
 * places is one decision rather than one per screen.
 */

/** Display precision for token amounts. The ledger keeps 18; people read 2. */
export const MONEY_DECIMALS = 2;

/**
 * Format a raw token amount for display, e.g. "1.000000000000000000" -> "1.00".
 *
 * Locale is pinned rather than inferred: these components render on the server
 * first, and a runtime-dependent format would differ from the browser's and
 * break hydration.
 *
 * An em dash is returned for a missing or non-numeric value instead of the
 * `NaN` a raw interpolation would show.
 */
export function formatAmount(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) return "—";
  return num.toLocaleString("en-US", {
    minimumFractionDigits: MONEY_DECIMALS,
    maximumFractionDigits: MONEY_DECIMALS,
  });
}
