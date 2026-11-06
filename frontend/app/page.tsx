import Link from "next/link";

import ArenaBoard from "@/components/ArenaBoard";
import StatStrip from "@/components/StatStrip";
import { ArrowRightIcon, CompassIcon, CoinsIcon, TrophyIcon, UsersIcon } from "@/components/icons";
import { ProgressBar } from "@/components/ui";
import { apiRequest } from "@/lib/api";
import { formatAmount } from "@/lib/money";
import { getPlatformStats } from "@/lib/stats";
import { getLeaderboard } from "@/services/leaderboard";
import type { Campaign, Leaderboard } from "@/types";

/** Compact form for a raw token amount: "1.2M", "8.4k", "912". */
function compact(value: string): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

/** A request that must not take the page down with it. */
async function safe<T>(promise: Promise<T>, fallback: T): Promise<T> {
  try {
    return await promise;
  } catch {
    return fallback;
  }
}

function budgetUsed(campaign: Campaign): number {
  const budget = Number(campaign.budget);
  const remaining = Number(campaign.remaining_budget);
  if (!Number.isFinite(budget) || budget <= 0 || !Number.isFinite(remaining)) return 0;
  return Math.max(0, Math.min(100, ((budget - remaining) / budget) * 100));
}

function endLabel(value: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

/**
 * The landing page — a live data surface, not a brochure.
 *
 * Everything on it comes from the platform's own endpoints: the arena board,
 * the campaign table, the headline figures. When an endpoint is unavailable the
 * section says so; nothing is filled with an invented number.
 */
export default async function HomePage() {
  const [stats, campaigns, board] = await Promise.all([
    getPlatformStats(),
    safe(apiRequest<Campaign[]>("/api/v1/campaigns/"), [] as Campaign[]),
    safe(getLeaderboard({ limit: 20 }), null as Leaderboard | null),
  ]);

  const live = campaigns.filter((campaign) => campaign.status === "ACTIVE");
  const cards = stats
    ? [
        { label: "Rewards paid", value: compact(stats.rewards_paid_total), icon: CoinsIcon },
        { label: "Claims settled", value: stats.claims_completed.toLocaleString("en-US"), icon: TrophyIcon },
        { label: "Active creators", value: stats.active_sellers.toLocaleString("en-US"), icon: UsersIcon },
        { label: "Campaigns live", value: stats.campaigns_live.toLocaleString("en-US"), icon: CompassIcon },
      ]
    : [];

  return (
    <div className="container section">
      <section className="arena-band">
        <div className="arena-band-row">
          <div>
            <span className="eyebrow">Live on Robinhood Chain</span>
            <h1>Track your voice with bagworkRH</h1>
            <p>
              Publish original posts for a campaign, and bagworkRH verifies them and pays you
              in stablecoin on-chain. Every figure below is settled money — no estimates.
            </p>
          </div>
          <div className="actions" style={{ marginTop: 0 }}>
            <Link href="/dashboard" className="btn btn-primary">
              View your card <ArrowRightIcon size={16} />
            </Link>
            <Link href="/leaderboard" className="btn btn-outline">
              Explore the arena
            </Link>
          </div>
        </div>
      </section>

      <StatStrip cards={cards} entries={board?.entries ?? []} />

      <section style={{ marginTop: 24 }}>
        <ArenaBoard initialBoard={board} campaigns={campaigns} />
      </section>

      <section className="card" style={{ marginTop: 16 }}>
        <div className="board-head">
          <div className="board-title">
            <h2>Live campaigns</h2>
            <span className="muted" style={{ fontSize: "0.82rem" }}>
              what brands are paying for right now
            </span>
          </div>
          <Link href="/campaigns" className="btn btn-outline btn-sm">
            All campaigns <ArrowRightIcon size={14} />
          </Link>
        </div>

        {live.length === 0 ? (
          <p className="muted">No campaign is live at the moment. Check back soon.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Campaign</th>
                  <th>Brand</th>
                  <th style={{ textAlign: "right" }}>Reward / post</th>
                  <th style={{ textAlign: "right" }}>Budget paid out</th>
                  <th style={{ textAlign: "right" }}>Ends</th>
                </tr>
              </thead>
              <tbody>
                {live.slice(0, 12).map((campaign, index) => {
                  const used = budgetUsed(campaign);
                  return (
                    <tr key={campaign.id}>
                      <td className="rank-cell">{index + 1}</td>
                      <td>
                        <Link href={`/campaigns/${campaign.slug}`} style={{ fontWeight: 600 }}>
                          {campaign.name}
                        </Link>
                      </td>
                      <td className="muted">{campaign.project_name}</td>
                      <td className="num-cell strong">
                        {formatAmount(campaign.reward_rate)} {campaign.token_symbol}
                      </td>
                      <td className="num-cell">
                        <span className="row" style={{ gap: 8, justifyContent: "flex-end", flexWrap: "nowrap" }}>
                          <span style={{ width: 72 }}>
                            <ProgressBar value={used} tone={used >= 90 ? "warn" : "brand"} />
                          </span>
                          <span>{Math.round(used)}%</span>
                        </span>
                      </td>
                      <td className="num-cell muted">{endLabel(campaign.end_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card" style={{ marginTop: 16 }}>
        <div className="split-even" style={{ display: "grid", gap: 20 }}>
          <div>
            <span className="eyebrow">For brands &amp; projects</span>
            <h2 style={{ marginBottom: 6 }}>Put a budget behind the posts you want</h2>
            <p className="muted" style={{ maxWidth: "58ch" }}>
              Fund a campaign in stablecoin, set a fixed reward per verified post, and watch
              it settle on-chain. Budgets are capped and reserved, payouts are bounded per
              account, and every financial change is written to an append-only audit trail.
            </p>
            <div className="actions">
              <Link href="/brand" className="btn btn-primary">
                Fund a campaign
              </Link>
              <Link href="/campaigns" className="btn btn-outline">
                See what is live
              </Link>
            </div>
          </div>
          <div className="panel">
            <div className="board-title" style={{ marginBottom: 10 }}>
              <h3 style={{ margin: 0 }}>How a payout settles</h3>
            </div>
            <ol style={{ margin: 0, paddingLeft: 18, color: "var(--text-2)", fontSize: "0.9rem" }}>
              <li style={{ marginBottom: 6 }}>You publish an original post for a campaign.</li>
              <li style={{ marginBottom: 6 }}>The platform discovers it and verifies it is original.</li>
              <li style={{ marginBottom: 6 }}>The reward is calculated server-side and reviewed.</li>
              <li>Your wallet claims it on-chain, signed with EIP-712.</li>
            </ol>
          </div>
        </div>
      </section>
    </div>
  );
}

