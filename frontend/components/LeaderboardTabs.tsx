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
type Tab = "creators" | "campaigns" | "brands";

/** Budget already committed: the budget minus what is left of it. */
function committed(campaign: Campaign): number {
  const budget = Number(campaign.budget);
  const remaining = Number(campaign.remaining_budget);
  if (!Number.isFinite(budget) || !Number.isFinite(remaining)) return 0;
  return Math.max(0, budget - remaining);
}

function delta(entry: LeaderboardEntry, period: Period): number {
  const raw = period === "7d" ? entry.delta_7d : entry.delta_30d;
  const value = Number(raw ?? 0);
  return Number.isFinite(value) ? value : 0;
}

function endLabel(value: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

/**
 * The full leaderboard: creators, campaigns and brands over the same data.
 *
 * "Creators" is the ranked board. "Campaigns" and "Brands" are the same money
 * grouped two other ways — the sector and region cuts of a Kaito-style page —
 * and they are derived from the campaign list the server already sent, so
 * switching tabs costs no request and shows no spinner.
 */
export default function LeaderboardTabs({
  initialBoard,
  campaigns,
}: {
  initialBoard: Leaderboard | null;
  campaigns: Campaign[];
}) {
  const { board, state, slug, setSlug, rangeIndex, setRangeIndex } =
    useLeaderboardBoard(initialBoard);
  const [tab, setTab] = useState<Tab>("creators");
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

  const totalCommitted = useMemo(
    () => campaigns.reduce((sum, campaign) => sum + committed(campaign), 0),
    [campaigns]
  );

  const campaignRows = useMemo(
    () => [...campaigns].sort((a, b) => committed(b) - committed(a)),
    [campaigns]
  );

  const brandRows = useMemo(() => {
    const map = new Map<string, { name: string; campaigns: number; committed: number; token: string }>();
    for (const campaign of campaigns) {
      const row =
        map.get(campaign.project_name) ??
        { name: campaign.project_name, campaigns: 0, committed: 0, token: campaign.token_symbol };
      row.campaigns += 1;
      row.committed += committed(campaign);
      map.set(campaign.project_name, row);
    }
    return Array.from(map.values()).sort((a, b) => b.committed - a.committed);
  }, [campaigns]);

  const TABS: { key: Tab; label: string }[] = [
    { key: "creators", label: "Creators" },
    { key: "campaigns", label: "Campaigns" },
    { key: "brands", label: "Brands" },
  ];

  return (
    <div className="card">
      <div className="board-head">
        <div className="board-title">
          <h2>Leaderboard</h2>
          <span className="muted" style={{ fontSize: "0.82rem" }}>
            settled rewards only
          </span>
        </div>
        <div className="seg" role="tablist" aria-label="Leaderboard view">
          {TABS.map((option) => (
            <button
              key={option.key}
              role="tab"
              aria-selected={tab === option.key}
              className={tab === option.key ? "is-active" : ""}
              onClick={() => setTab(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {tab === "creators" ? (
        <>
          <div className="board-head">
            <div className="board-controls">
              <span className="seg-label">Rank</span>
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
            </div>
            <div className="board-controls">
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
            <Skeleton lines={8} />
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
                  {entries.length} creators on this page · click a creator for their profile
                </span>
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
        </>
      ) : null}

      {tab === "campaigns" ? (
        campaignRows.length === 0 ? (
          <p className="muted">No campaigns yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Campaign</th>
                  <th>Brand</th>
                  <th style={{ textAlign: "right" }}>Reward / post</th>
                  <th style={{ textAlign: "right" }}>Committed</th>
                  <th style={{ textAlign: "right" }}>Share</th>
                  <th style={{ textAlign: "right" }}>Ends</th>
                </tr>
              </thead>
              <tbody>
                {campaignRows.map((campaign, index) => {
                  const used = committed(campaign);
                  const share = totalCommitted > 0 ? (used / totalCommitted) * 100 : 0;
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
                        {formatAmount(String(used))} {campaign.token_symbol}
                      </td>
                      <td className="num-cell">{share.toFixed(1)}%</td>
                      <td className="num-cell muted">{endLabel(campaign.end_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      ) : null}

      {tab === "brands" ? (
        brandRows.length === 0 ? (
          <p className="muted">No brands yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Brand</th>
                  <th style={{ textAlign: "right" }}>Campaigns</th>
                  <th style={{ textAlign: "right" }}>Committed</th>
                  <th style={{ textAlign: "right" }}>Share</th>
                </tr>
              </thead>
              <tbody>
                {brandRows.map((brand, index) => {
                  const share = totalCommitted > 0 ? (brand.committed / totalCommitted) * 100 : 0;
                  return (
                    <tr key={brand.name}>
                      <td className="rank-cell">{index + 1}</td>
                      <td style={{ fontWeight: 600 }}>{brand.name}</td>
                      <td className="num-cell">{brand.campaigns}</td>
                      <td className="num-cell">
                        {formatAmount(String(brand.committed))} {brand.token}
                      </td>
                      <td className="num-cell">{share.toFixed(1)}%</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      ) : null}

      <p className="muted" style={{ marginTop: 14, fontSize: "0.78rem" }}>
        Committed = a campaign&apos;s budget minus what remains of it: money promised to
        verified posts, including payouts still awaiting review.{" "}
        <Link href="/campaigns" className="row" style={{ display: "inline-flex", gap: 4 }}>
          Browse campaigns <ArrowRightIcon size={12} />
        </Link>
      </p>
    </div>
  );
}

