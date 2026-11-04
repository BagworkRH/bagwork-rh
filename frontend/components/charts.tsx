/**
 * Chart primitives.
 *
 * Bars are plain flex divs rather than SVG or a charting library: a 30-day
 * earnings series is a handful of rectangles, the divs reflow for free on a
 * phone, and a charting dependency would be the largest thing in the bundle.
 * Values are scaled to the series maximum so the shape shows momentum.
 */
import { formatAmount } from "@/lib/money";

export function BarSeries({
  values,
  labels,
  tone = "brand",
  height = 160,
  unit = "",
}: {
  values: number[];
  labels?: string[];
  tone?: "brand" | "green";
  height?: number;
  unit?: string;
}) {
  if (values.length === 0) {
    return <p className="muted">No data for this period yet.</p>;
  }
  const max = Math.max(...values, 0);
  const total = values.reduce((sum, value) => sum + value, 0);

  return (
    <div>
      <div className="bar-chart" style={{ height }}>
        {values.map((value, index) => {
          const pct = max === 0 ? 0 : Math.max(2, (value / max) * 100);
          const label = labels?.[index] ?? `Day ${index + 1}`;
          return (
            <div className="bar-col" key={index} title={`${label}: ${formatAmount(value)}${unit ? ` ${unit}` : ""}`}>
              <div
                className="bar-fill"
                style={{
                  height: `${pct}%`,
                  background: tone === "green" ? "var(--accent-2)" : undefined,
                }}
              />
            </div>
          );
        })}
      </div>
      <div className="campaign-progress-meta" style={{ marginTop: 8 }}>
        <span>{labels?.[0] ?? "Start"}</span>
        <span>
          {formatAmount(total)}
          {unit ? ` ${unit}` : ""} total
        </span>
        <span>{labels?.[labels.length - 1] ?? "Today"}</span>
      </div>
    </div>
  );
}
