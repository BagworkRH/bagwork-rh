/**
 * A tiny earnings sparkline.
 *
 * Inline SVG rather than a chart library: this is ~25 lines, costs nothing in
 * bundle size, and a library would become the largest dependency in the app to
 * draw one line. Values are scaled to the series maximum, so the shape shows
 * momentum rather than absolute size.
 */
export default function Sparkline({
  values,
  tone = "up",
  height = 32,
}: {
  values: number[];
  tone?: "up" | "down" | "flat";
  height?: number;
}) {
  if (values.length < 2) return <span className="sparkline-empty" aria-hidden="true" />;

  const width = 100;
  const max = Math.max(...values, 0);
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      // A flat series sits on the floor rather than the ceiling: a line across
      // the top would read as "earning a lot" when it means "nothing yet".
      const y = max === 0 ? height - 1 : height - (value / max) * (height - 2) - 1;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  const stroke =
    tone === "down" ? "var(--danger)" : tone === "flat" ? "var(--muted)" : "var(--accent-2)";

  return (
    <svg
      className="sparkline"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="Earnings trend"
    >
      <polyline
        points={points}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
