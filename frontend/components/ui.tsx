/**
 * Small presentational primitives shared across the app.
 *
 * Each is a thin wrapper over a class in `globals.css` — the markup stays in
 * one place so a stat tile looks identical on the dashboard, in the arena and
 * in the ops console, and a change to spacing is a change to one file.
 */
import type { ComponentType, ReactNode } from "react";

export type Tone = "brand" | "green" | "blue" | "warn";

const TONE_CLASS: Record<Tone, string> = {
  brand: "",
  green: "icon-green",
  blue: "icon-blue",
  warn: "icon-warn",
};

export function StatTile({
  label,
  value,
  unit,
  icon: Icon,
  tone = "brand",
  sub,
  trend,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  icon?: ComponentType<{ size?: number }>;
  tone?: Tone;
  sub?: ReactNode;
  trend?: { direction: "up" | "down"; text: string };
}) {
  return (
    <div className="stat-tile">
      <div className="stat-tile-head">
        {Icon ? (
          <span className={`stat-icon ${TONE_CLASS[tone]}`}>
            <Icon size={18} />
          </span>
        ) : null}
        <span className="stat-label">{label}</span>
      </div>
      <div className="stat-value">
        {value}
        {unit ? <small> {unit}</small> : null}
      </div>
      {(sub || trend) && (
        <div className="stat-foot">
          {trend ? (
            <span className={`stat-trend ${trend.direction}`}>
              {trend.direction === "up" ? "▲" : "▼"} {trend.text}
            </span>
          ) : null}
          {sub}
        </div>
      )}
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon?: ComponentType<{ size?: number }>;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      {Icon ? (
        <span className="empty-icon">
          <Icon size={22} />
        </span>
      ) : null}
      <h3>{title}</h3>
      {children ? <p>{children}</p> : null}
      {action ? <div className="actions" style={{ justifyContent: "center" }}>{action}</div> : null}
    </div>
  );
}

export function ProgressBar({
  value,
  tone = "brand",
  label,
}: {
  /** 0..100. Values outside the range are clamped. */
  value: number;
  tone?: "brand" | "green" | "warn" | "danger";
  label?: string;
}) {
  const pct = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  const toneClass = tone === "brand" ? "" : `is-${tone}`;
  return (
    <div
      className="progress"
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <div className={`progress-bar ${toneClass}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Skeleton({ lines = 3, card = false }: { lines?: number; card?: boolean }) {
  if (card) return <div className="skeleton skeleton-card" aria-hidden="true" />;
  return (
    <div aria-hidden="true">
      {Array.from({ length: lines }).map((_, index) => (
        <div
          key={index}
          className="skeleton skeleton-line"
          style={{ width: index === lines - 1 ? "60%" : "100%" }}
        />
      ))}
    </div>
  );
}

export function StatGridSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="stat-grid" aria-hidden="true">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="skeleton" style={{ height: 118, borderRadius: 12 }} />
      ))}
    </div>
  );
}

export function CardSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="grid" aria-hidden="true">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="skeleton skeleton-card" />
      ))}
    </div>
  );
}

export function Avatar({
  name,
  src,
  size = "md",
}: {
  name: string;
  src?: string | null;
  size?: "sm" | "md" | "lg";
}) {
  const cls = `avatar ${size === "sm" ? "avatar-sm" : size === "lg" ? "avatar-lg" : ""}`;
  if (src) {
    // Remote avatars are not routed through the optimizer on purpose (it needs
    // `sharp`, which this image deliberately does not ship).
    // eslint-disable-next-line @next/next/no-img-element
    return <img className={cls} src={src} alt="" loading="lazy" />;
  }
  const initials = name.trim().slice(0, 2).toUpperCase() || "?";
  return (
    <span className={cls} aria-hidden="true">
      {initials}
    </span>
  );
}

export function Pagination({
  offset,
  limit,
  count,
  onChange,
}: {
  offset: number;
  limit: number;
  count: number;
  onChange: (nextOffset: number) => void;
}) {
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(count / limit));
  if (count <= limit) return null;
  return (
    <div className="pagination">
      <button
        className="btn btn-outline btn-sm"
        onClick={() => onChange(Math.max(0, offset - limit))}
        disabled={offset <= 0}
      >
        Previous
      </button>
      <span className="page-info">
        Page {page} of {pages}
      </span>
      <button
        className="btn btn-outline btn-sm"
        onClick={() => onChange(offset + limit)}
        disabled={offset + limit >= count}
      >
        Next
      </button>
    </div>
  );
}
