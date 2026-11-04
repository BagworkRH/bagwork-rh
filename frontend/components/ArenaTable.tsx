import Link from "next/link";

import DeltaChip from "@/components/DeltaChip";
import { Avatar } from "@/components/ui";
import { formatAmount } from "@/lib/money";
import type { LeaderboardEntry } from "@/types";

/**
 * One board, one table.
 *
 * Shared by the landing page and the full leaderboard so a row looks and links
 * identically in both — and so a creator's name is a link to their profile
 * everywhere it appears. `rewardsColumn` swaps the figure for the reward count,
 * which is the only difference between the earnings board and the trending one.
 */
export default function ArenaTable({
  entries,
  symbol,
  metric,
  period,
  rewardsColumn = false,
  startRank,
}: {
  entries: LeaderboardEntry[];
  symbol: string;
  metric: "earned" | "share";
  period: "7d" | "30d";
  rewardsColumn?: boolean;
  /** Override the printed rank (the trending table re-numbers its own rows). */
  startRank?: number;
}) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Creator</th>
          <th style={{ textAlign: "right" }}>
            {rewardsColumn ? "Rewards" : metric === "share" ? "Share" : "Earned"}
          </th>
          <th style={{ textAlign: "right" }}>Δ {period === "7d" ? "7D" : "30D"}</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((entry, index) => (
          <tr key={`${entry.rank}-${entry.seller_code}`}>
            <td className="rank-cell">{startRank ? startRank + index : entry.rank}</td>
            <td>
              <Link href={`/creators/${entry.seller_code}`} className="name-cell">
                <Avatar name={entry.display_name} src={entry.avatar_url} size="sm" />
                <span className="who">
                  <span className="nm">{entry.display_name}</span>
                  {entry.username ? <span className="hd">@{entry.username}</span> : null}
                </span>
                {entry.demo ? <span className="demo-chip">demo</span> : null}
              </Link>
            </td>
            <td className="num-cell strong">
              {rewardsColumn ? (
                entry.rewards
              ) : entry.hidden ? (
                <span className="muted">Hidden</span>
              ) : metric === "share" ? (
                `${((entry.share ?? 0) * 100).toFixed(2)}%`
              ) : (
                <>
                  {formatAmount(entry.earned ?? "0")} <span className="muted">{symbol}</span>
                </>
              )}
            </td>
            <td className="num-cell">
              <DeltaChip value={period === "7d" ? entry.delta_7d : entry.delta_30d} symbol={symbol} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
