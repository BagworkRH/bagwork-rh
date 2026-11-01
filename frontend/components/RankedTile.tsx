import { formatAmount } from "@/lib/money";
import type { LeaderboardEntry } from "@/types";

import Sparkline from "./Sparkline";

function initials(name: string) {
  return name.trim().slice(0, 2).toUpperCase() || "?";
}

/**
 * One creator in the arena: rank, identity, what they earned, and the shape of
 * how they earned it.
 *
 * The tile colour encodes movement, so the board reads at a glance without
 * reading numbers - which is most of what makes a leaderboard fun. A creator who
 * hid their earnings keeps the tile and loses the figure; showing "0" instead
 * would be a claim we cannot make.
 */
export default function RankedTile({
  entry,
  symbol,
}: {
  entry: LeaderboardEntry;
  symbol: string;
}) {
  const delta = Number(entry.delta_7d ?? 0);
  const tone = entry.hidden ? "flat" : delta > 0 ? "up" : delta < 0 ? "down" : "flat";
  const medal = entry.rank <= 3 ? `tile-medal-${entry.rank}` : "";

  return (
    <article className={`tile tile-${tone} ${medal}`}>
      <header className="tile-head">
        {entry.avatar_url ? (
          /* eslint-disable-next-line @next/next/no-img-element -- remote avatar; the
             optimizer needs sharp, which this image deliberately does not ship */
          <img
            className="tile-avatar"
            src={entry.avatar_url}
            alt=""
            width={28}
            height={28}
            loading="lazy"
          />
        ) : (
          <span className="tile-avatar tile-initials" aria-hidden="true">
            {initials(entry.display_name)}
          </span>
        )}
        <span
          className="tile-name"
          title={entry.username ? `@${entry.username}` : entry.display_name}
        >
          {entry.display_name}
        </span>
        <span className="tile-rank">{entry.rank}</span>
      </header>

      {entry.hidden ? (
        <p className="tile-figure muted">Earnings hidden</p>
      ) : (
        <p className="tile-figure">
          {formatAmount(entry.earned ?? "0")} <small>{symbol}</small>
        </p>
      )}

      {!entry.hidden && <Sparkline values={entry.series} tone={tone} />}
    </article>
  );
}
