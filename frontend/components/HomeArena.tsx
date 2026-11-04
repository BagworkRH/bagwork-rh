"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import ArenaTable from "@/components/ArenaTable";
import { BarSeries } from "@/components/charts";
import { ArrowRightIcon, TrendUpIcon, TrophyIcon } from "@/components/icons";
import { EmptyState, Skeleton } from "@/components/ui";
import { BOARD_RANGES, useLeaderboardBoard } from "@/hooks/useLeaderboardBoard";
import { formatAmount } from "@/lib/money";
import type { Campaign, Leaderboard, LeaderboardEntry } from "@/types";

type Period = "7d" | "30d";

/** Movement for the selected period; a hidden or missing figure counts as 0. */
function delta(entry: LeaderboardEntry, period: Period): number {
  const raw = period === "7d" ? entry.delta_7d : entry.delta_30d;
  const value = Number(raw ?? 0);
  return Number.isFinite(value) ? value : 0;
}

/**
 * The arena board on the landing page.
 *
 * Same shape as the full leaderboard, sized for a first impression: the ranks,
 * a range selector, a period toggle, and a switch between absolute earnings and
 * each creator's share of the board. Everything here is settled money — the
 * server sends null for a creator who hid their earnings, and the table prints
 * "Hidden" rather than a zero it cannot stand behind.
 */
export default function HomeArena({
  initialBoard,
  campaigns,
}: {
  initialBoard: Leaderboard | null;
  campaigns: Campaign[];
}) {
  const { board, state, slug, setSlug, rangeIndex, setRangeIndex } =
    useLeaderboardBoard(initialBoard);
  const [period, setPeriod] = useState<Period>("7d");
  const [metric, setMetric] = useState<"earned" | "share">("earned");

  const entries = useMemo(() => board?.entries ?? [], [board]);
  const symbol = board?.campaign?.token_symbol ?? "";
  const activeCampaigns = useMemo(
    () => campaigns.filter((campaign) => campaign.status === "ACTIVE"),
    [campaigns]
  );

  const topGainer = useMemo(() => {
    const visible = entries.filter((entry) => !entry.hidden);
    if (visible.length === 0) return null;
    return visible.reduce((best, entry) => (delta(entry, period) > delta(best, period) ? entry : best));
  }, [entries, period]);

  // A board-level series: the sum of each creator's daily totals. Real money,
  // not a decorative curve.
  const aggregate = useMemo(() => {
    const visible = entries.filter((entry) => !entry.hidden && entry.series.length > 0);
    if (visible.length === 0) return [];
    const length = Math.max(...visible.map((entry) => entry.series.length));
    const out = new Array<number>(length).fill(0);
    for (const entry of visible) {
      const offset = length - entry.series.length;
      entry.series.forEach((value, index) => {
        out[offset + index] += value;
      });
    }
    return out;
  }, [entries]);

  const trending = useMemo(
    () => [...entries].sort((a, b) => b.rewards - a.rewards).slice(0, 10),
    [entries]
  );

  return (
    <>
      <div className="card">
        <div className="board-head">
          <div className="board-title">
            <h2>Creator Arena</h2>
            {board?.campaign ? (
              <span className="muted" style={{ fontSize: "0.82rem" }}>
                {board.campaign.name}
              </span>
            ) : null}
            {board?.has_demo ? <span className="demo-chip">includes demo</span> : null}
          </div>
          <div className="board-controls">
            <div className="seg" role="group" aria-label="Rank range">
              {BOARD_RANGES.map((range, index) => (
                <button
                  key={range.label}
                  className={index === rangeIndex ? "is-active" : ""}
                  onClick={() => setRangeIndex(index)}
                  aria-pressed={index === rangeIndex}
                >
                  {range.label}
                </button>
              ))}
            </div>
            <div className="seg" role="group" aria-label="Period">
              <button className={period === "7d" ? "is-active" : ""} onClick={() => setPeriod("7d")} aria-pressed={period === "7d"}>
                7D
              </button>
              <button className={period === "30d" ? "is-active" : ""} onClick={() => setPeriod("30d")} aria-pressed={period === "30d"}>
                30D
              </button>
            </div>
            <div className="seg" role="group" aria-label="Metric">
              <button className={metric === "earned" ? "is-active" : ""} onClick={() => setMetric("earned")} aria-pressed={metric === "earned"}>
                Absolute
              </button>
              <button className={metric === "share" ? "is-active" : ""} onClick={() => setMetric("share")} aria-pressed={metric === "share"}>
                Relative (%)
              </button>
            </div>
          </div>
        </div>

        {activeCampaigns.length > 1 ? (
          <div className="filter-chips">
            <button className={`filter-chip ${slug === "" ? "is-active" : ""}`} onClick={() => setSlug("")}>
              All campaigns
            </button>
            {activeCampaigns.map((campaign) => (
              <button
                key={campaign.id}
                className={`filter-chip ${slug === campaign.slug ? "is-active" : ""}`}
                onClick={() => setSlug(campaign.slug)}
              >
                {campaign.name}
              </button>
            ))}
          </div>
        ) : null}

        {topGainer ? (
          <div className="gainer" style={{ marginBottom: 14 }}>
            <TrendUpIcon size={18} />
            <div>
              <div className="label">Top gainer · {period === "7d" ? "7D" : "30D"}</div>
              <div style={{ fontWeight: 600 }}>
                {topGainer.display_name}
                {topGainer.username ? <span className="muted"> @{topGainer.username}</span> : null}
              </div>
            </div>
            <span className="money num" style={{ marginLeft: "auto", fontWeight: 700 }}>
              ▲ {formatAmount(String(delta(topGainer, period)))} {symbol}
            </span>
          </div>
        ) : null}

        {state === "loading" ? (
          <Skeleton lines={6} />
        ) : state === "error" ? (
          <div className="banner banner-error">Could not load the board. Refresh to try again.</div>
        ) : entries.length === 0 ? (
          <EmptyState
            icon={TrophyIcon}
            title="No one has been paid yet"
            action={
              <Link href="/campaigns" className="btn btn-primary btn-sm">
                Browse campaigns
              </Link>
            }
          >
            This board fills the moment a creator&apos;s reward is settled. Nothing here is
            estimated — every figure is money that actually moved.
          </EmptyState>
        ) : (
          <>
            <div className="table-wrap scroll-y">
              <ArenaTable entries={entries} symbol={symbol} metric={metric} period={period} />
            </div>
            <div className="actions" style={{ justifyContent: "space-between" }}>
              <span className="muted" style={{ fontSize: "0.78rem" }}>
                {entries.length} creators on this board · settled rewards only
              </span>
              <Link href="/leaderboard" className="btn btn-outline btn-sm">
                Explore full leaderboard <ArrowRightIcon size={14} />
              </Link>
            </div>
          </>
        )}

        <div style={{ marginTop: 18 }}>
          <div className="board-title" style={{ marginBottom: 10 }}>
            <h3 style={{ margin: 0 }}>Daily payouts on this board</h3>
            <span className="muted" style={{ fontSize: "0.78rem" }}>
              last {board?.series_days ?? 30} days
            </span>
          </div>
          {aggregate.length > 1 ? (
            <BarSeries values={aggregate} tone="green" unit={symbol} />
          ) : (
            <p className="muted">Not enough history on this board yet.</p>
          )}
        </div>
      </div>

      {trending.length > 0 ? (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="board-head">
            <div className="board-title">
              <h2>Trending creators</h2>
              <span className="muted" style={{ fontSize: "0.82rem" }}>
                by rewards settled
              </span>
            </div>
            <Link href="/leaderboard" className="muted" style={{ fontSize: "0.8125rem" }}>
              Full leaderboard
            </Link>
          </div>
          <div className="table-wrap">
            <ArenaTable
              entries={trending}
              symbol={symbol}
              metric={metric}
              period={period}
              rewardsColumn
              startRank={1}
            />
          </div>
        </div>
      ) : null}
    </>
  );
}

