"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Avatar } from "@/components/ui";
import { DeltaCell } from "@/components/ArenaBoard";
import { formatAmount } from "@/lib/money";
import type { LeaderboardEntry } from "@/types";

type Period = "7d" | "30d";
type Metric = "earned" | "share";

function delta(entry: LeaderboardEntry, period: Period): number {
  const raw = period === "7d" ? entry.delta_7d : entry.delta_30d;
  const value = Number(raw ?? 0);
  return Number.isFinite(value) ? value : 0;
}

/**
 * Top Gainer rail — the same component used inside ArenaBoard, extracted so it
 * can render anywhere (including the landing page toggle that replaces the
 * stat box). Manages its own `period` and `metric` state so it is fully
 * self-contained.
 */
export default function TopGainersRail({
  entries,
}: {
  entries: LeaderboardEntry[];
}) {
  const [period, setPeriod] = useState<Period>("7d");
  const [metric, setMetric] = useState<Metric>("earned");

  const railRows = useMemo(
    () =>
      [...entries]
        .sort((a, b) => delta(b, period) - delta(a, period))
        .slice(0, 10),
    [entries, period]
  );

  function currentFigure(entry: LeaderboardEntry) {
    if (entry.hidden) return <span className="muted">Hidden</span>;
    if (metric === "share")
      return `${((entry.share ?? 0) * 100).toFixed(2)}%`;
    return formatAmount(entry.earned ?? "0");
  }

  return (
    <div className="rail-card">
      <div className="rail-head">
        <h3>Top Gainer</h3>
        <div className="seg" role="group" aria-label="Metric">
          <button
            className={metric === "earned" ? "is-active" : ""}
            onClick={() => setMetric("earned")}
            aria-pressed={metric === "earned"}
          >
            Absolute
          </button>
          <button
            className={metric === "share" ? "is-active" : ""}
            onClick={() => setMetric("share")}
            aria-pressed={metric === "share"}
          >
            Relative (%)
          </button>
        </div>
      </div>
      {railRows.length === 0 ? (
        <p className="muted" style={{ fontSize: "0.85rem" }}>
          Nothing to rank yet.
        </p>
      ) : (
        <table className="rail-list">
          <thead>
            <tr>
              <th>Name</th>
              <th className="r">Current</th>
              <th className="r">Δ 7D</th>
              <th className="r">Δ 30D</th>
            </tr>
          </thead>
          <tbody>
            {railRows.map((entry) => (
              <tr key={`${entry.rank}-${entry.seller_code}`}>
                <td>
                  <Link
                    href={`/creators/${entry.seller_code}`}
                    className="rail-name"
                  >
                    <Avatar
                      name={entry.display_name}
                      src={entry.avatar_url}
                      size="sm"
                    />
                    <span className="who">
                      <span className="nm">{entry.display_name}</span>
                      {entry.username ? (
                        <span className="hd">{entry.username}</span>
                      ) : null}
                    </span>
                  </Link>
                </td>
                <td className="r">{currentFigure(entry)}</td>
                <td className="r">
                  <DeltaCell value={entry.delta_7d} />
                </td>
                <td className="r">
                  <DeltaCell value={entry.delta_30d} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
