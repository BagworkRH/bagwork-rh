import { formatAmount } from "@/lib/money";

/**
 * A movement figure with a direction arrow.
 *
 * The arrow carries the meaning, so the colour is a reinforcement rather than
 * the only signal - which matters for anyone who cannot distinguish the two
 * shades. A null value means the creator hid their earnings: that is shown as a
 * dash, never as zero, because "0" would be a claim we cannot make.
 */
export default function DeltaChip({
  value,
  symbol,
}: {
  value: string | null;
  symbol: string;
}) {
  if (value === null) return <span className="muted">—</span>;

  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric === 0) return <span className="muted">—</span>;

  const up = numeric > 0;
  return (
    <span className={`delta ${up ? "delta-up" : "delta-down"}`}>
      {up ? "▲" : "▼"} {formatAmount(value)} {symbol}
    </span>
  );
}
