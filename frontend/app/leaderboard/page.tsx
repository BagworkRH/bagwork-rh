import LeaderboardTabs from "@/components/LeaderboardTabs";
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
  title: "Leaderboard — bagworkRH",
  description:
    "What creators actually earned, ranked by creator, campaign and brand. Settled rewards only.",
};

/**
 * The full leaderboard.
 *
 * Server-rendered so the default board is real on first paint; the tabs and the
 * range/period/metric controls are layered on by the client component.
 */
export default async function LeaderboardPage() {
  const [campaigns, board] = await Promise.all([
    safe(apiRequest<Campaign[]>("/api/v1/campaigns/"), [] as Campaign[]),
    safe(getLeaderboard({ limit: 20 }), null as Leaderboard | null),
  ]);

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="page-head">
        <div>
          <span className="eyebrow">Arena</span>
          <h1>Leaderboard</h1>
          <p className="lede">
            What creators actually earned — by creator, by campaign, by brand. Only settled
            rewards appear, and anyone who hides their earnings keeps their place without
            the figure.
          </p>
        </div>
      </div>

      <LeaderboardTabs initialBoard={board} campaigns={campaigns} />
    </div>
  );
}
