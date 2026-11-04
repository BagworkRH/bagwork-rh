import ArenaBoard from "@/components/ArenaBoard";
import SectorTables from "@/components/SectorTables";
import { apiRequest } from "@/lib/api";
import { getLeaderboard } from "@/services/leaderboard";
import type { Campaign, Leaderboard } from "@/types";

/** A request that must not take the page down with it. */
async function safe<T>(promise: Promise<T>, fallback: T): Promise<T> {
  try {
    return await promise;
  } catch {
    return fallback;
  }
}

export const metadata = {
  title: "Mindshare Arena — bagworkRH",
  description:
    "What creators actually earned, ranked by creator, campaign and brand. Settled rewards only.",
};

/**
 * The board is live money, so this page must not be prerendered.
 *
 * Without this the page is statically generated at build time and its HTML is
 * frozen: the board kept showing the creators and names it had on the day of the
 * deploy, and only the client re-fetch corrected it after hydration. The fetch
 * helper sets no cache policy, so nothing else here opts the route out.
 */
export const dynamic = "force-dynamic";

/**
 * The arena.
 *
 * Server-rendered so the board is real on first paint; the tabs, ranges and
 * metric switches are layered on by the client component.
 */
export default async function LeaderboardPage() {
  const [campaigns, board] = await Promise.all([
    safe(apiRequest<Campaign[]>("/api/v1/campaigns/"), [] as Campaign[]),
    safe(getLeaderboard({ limit: 20 }), null as Leaderboard | null),
  ]);

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="arena-band">
        <span className="eyebrow">Arena</span>
        <h1>Top Voices Creator Arena</h1>
        <p>
          What creators actually earned — by creator, by campaign, by brand. Only settled
          rewards appear, and anyone who hides their earnings keeps their place without the
          figure.
        </p>
      </div>

      <ArenaBoard initialBoard={board} campaigns={campaigns} />
      <SectorTables campaigns={campaigns} />
    </div>
  );
}

