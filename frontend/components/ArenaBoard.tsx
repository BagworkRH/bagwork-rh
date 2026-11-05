"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { CSSProperties } from "react";

import { BarSeries } from "@/components/charts";
import { InfoIcon, TrophyIcon } from "@/components/icons";
import Sparkline from "@/components/Sparkline";
import { Avatar, EmptyState, Skeleton } from "@/components/ui";
import { BOARD_RANGES, useLeaderboardBoard } from "@/hooks/useLeaderboardBoard";
import { formatAmount } from "@/lib/money";
import type { Campaign, Leaderboard, LeaderboardEntry } from "@/types";

type Period = "7d" | "30d";
type Metric = "earned" | "share";

function delta(entry: LeaderboardEntry, period: Period): number {
  const raw = period === "7d" ? entry.delta_7d : entry.delta_30d;
  const value = Number(raw ?? 0);
  return Number.isFinite(value) ? value : 0;
}

function tone(entry: LeaderboardEntry, period: Period): "up" | "down" | "flat" {
  if (entry.hidden) return "flat";
  const value = delta(entry, period);
  return value > 0 ? "up" : value < 0 ? "down" : "flat";
}

/**
 * Category art for a tab.
 *
 * Kaito backs each tab with a photograph. We have no photography and will not
 * fake any, so each campaign gets a stable dark gradient derived from its name:
 * recognisable row to row, and honestly ours.
 */
function tabArt(name: string): string {
  let hash = 0;
  for (let index = 0; index < name.length; index += 1) {
    hash = (hash * 31 + name.charCodeAt(index)) % 360;
  }
  const second = (hash + 52) % 360;
  return `linear-gradient(135deg, hsl(${hash} 62% 24%), hsl(${second} 66% 13%))`;
}

/** A signed movement figure for the rail. */
function DeltaCell({ value }: { value: string | null }) {
  const numeric = Number(value ?? 0);
  if (!Number.isFinite(numeric) || numeric === 0) return <span className="muted">—</span>;
  const up = numeric > 0;
  return (
    <span className={up ? "delta-up" : "delta-down"}>
      {up ? "▲" : "▼"} {formatAmount(String(Math.abs(numeric)))}
    </span>
  );
}

/**
 * The arena: category tabs, a rank range, the tile grid, and the Top Gainer
 * rail. Shared by the landing page and `/leaderboard` so both show the same
 * board — a visitor who likes what they see on the front page finds exactly it
 * again one click later.
 */
export default function ArenaBoard({
  initialBoard,
  campaigns,
  showCampaignTabs = true,
}: {
  initialBoard: Leaderboard | null;
  campaigns: Campaign[];
  showCampaignTabs?: boolean;
}) {
  const { board, state, slug, setSlug, rangeIndex, setRangeIndex } =
    useLeaderboardBoard(initialBoard);
  const [period, setPeriod] = useState<Period>("7d");
  const [metric, setMetric] = useState<Metric>("earned");

  const entries = useMemo(() => board?.entries ?? [], [board]);
  const symbol = board?.campaign?.token_symbol ?? "";
  const activeCampaigns = useMemo(
    () => campaigns.filter((campaign) => campaign.status === "ACTIVE"),
    [campaigns]
  );

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

  const railRows = useMemo(
    () => [...entries].sort((a, b) => delta(b, period) - delta(a, period)).slice(0, 10),
    [entries, period]
  );

  function currentFigure(entry: LeaderboardEntry) {
    if (entry.hidden) return <span className="muted">Hidden</span>;
    if (metric === "share") return `${((entry.share ?? 0) * 100).toFixed(2)}%`;
    return formatAmount(entry.earned ?? "0");
  }

  return (
    <div className="arena-split">
      <div>
        {showCampaignTabs && activeCampaigns.length > 1 ? (
          <div className="voice-tabs">
            <button
              className={`voice-tab ${slug === "" ? "is-active" : ""}`}
              style={{ "--tab-art": tabArt("All campaigns") } as CSSProperties}
              onClick={() => setSlug("")}
            >
              <span>All campaigns</span>
            </button>
            {activeCampaigns.map((campaign) => (
              <button
                key={campaign.id}
                className={`voice-tab ${slug === campaign.slug ? "is-active" : ""}`}
                style={{ "--tab-art": tabArt(campaign.name) } as CSSProperties}
                onClick={() => setSlug(campaign.slug)}
              >
                <span>{campaign.name}</span>
              </button>
            ))}
          </div>
        ) : null}

        <div className="board-head">
          <div className="range-path">
            {BOARD_RANGES.map((range, index) => (
              <span key={range.label} className="row" style={{ gap: 12 }}>
                {index > 0 ? <span className="range-sep">›</span> : null}
                <button
                  className={`range-step ${index === rangeIndex ? "is-active" : ""}`}
                  onClick={() => setRangeIndex(index)}
                  aria-pressed={index === rangeIndex}
                >
                  <span className="dot" />
                  {range.label}
                </button>
              </span>
            ))}
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
          </div>
        </div>

        {state === "loading" ? (
          <div className="tile-grid" aria-hidden="true">
            {Array.from({ length: 8 }).map((_, index) => (
              <div key={index} className="skeleton" style={{ height: 186, borderRadius: 12 }} />
            ))}
          </div>
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
            <div className="tile-grid">
              {entries.map((entry) => (
                <VoiceTile
                  key={`${entry.rank}-${entry.seller_code}`}
                  entry={entry}
                  symbol={symbol}
                  metric={metric}
                  period={period}
                />
              ))}
            </div>

            <div className="board-title" style={{ margin: "22px 0 10px" }}>
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
          </>
        )}
      </div>

      <aside className="rail">
        <div className="rail-card">
          <div className="rail-head">
            <h3>Top Gainer</h3>
            <div className="seg" role="group" aria-label="Metric">
              <button className={metric === "earned" ? "is-active" : ""} onClick={() => setMetric("earned")} aria-pressed={metric === "earned"}>
                Absolute
              </button>
              <button className={metric === "share" ? "is-active" : ""} onClick={() => setMetric("share")} aria-pressed={metric === "share"}>
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
                      <Link href={`/creators/${entry.seller_code}`} className="rail-name">
                        <Avatar name={entry.display_name} src={entry.avatar_url} size="sm" />
                        <span className="who">
                          <span className="nm">{entry.display_name}</span>
                          {entry.username ? <span className="hd">{entry.username}</span> : null}
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

        <div className="rail-card">
          <div className="rail-head">
            <h3>Board totals</h3>
            <InfoIcon size={15} />
          </div>
          <div className="stat-grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <div className="num" style={{ fontSize: "1.2rem", fontWeight: 700 }}>
                {formatAmount(board?.totals.paid ?? "0")}
              </div>
              <div className="muted" style={{ fontSize: "0.72rem" }}>
                Paid out {symbol}
              </div>
            </div>
            <div>
              <div className="num" style={{ fontSize: "1.2rem", fontWeight: 700 }}>
                {board?.totals.creators ?? 0}
              </div>
              <div className="muted" style={{ fontSize: "0.72rem" }}>
                Creators paid
              </div>
            </div>
            <div>
              <div className="num" style={{ fontSize: "1.2rem", fontWeight: 700 }}>
                {board?.totals.rewards ?? 0}
              </div>
              <div className="muted" style={{ fontSize: "0.72rem" }}>
                Rewards settled
              </div>
            </div>
            <div>
              <div className="num" style={{ fontSize: "1.2rem", fontWeight: 700 }}>
                {board?.series_days ?? 30}d
              </div>
              <div className="muted" style={{ fontSize: "0.72rem" }}>
                History shown
              </div>
            </div>
          </div>
          <p className="muted" style={{ fontSize: "0.72rem", marginTop: 10 }}>
            Settled rewards only. Wallet addresses are never shown.
          </p>
        </div>
      </aside>
    </div>
  );
}

function VoiceTile({
  entry,
  symbol,
  metric,
  period,
}: {
  entry: LeaderboardEntry;
  symbol: string;
  metric: Metric;
  period: Period;
}) {
  const direction = tone(entry, period);
  return (
    <Link
      href={`/creators/${entry.seller_code}`}
      className={`voice-tile ${direction} ${entry.rank === 1 ? "rank-1" : ""}`}
    >
      <div className="voice-tile-top">
        <Avatar name={entry.display_name} src={entry.avatar_url} />
        <span className="voice-rank">{entry.rank}</span>
      </div>

      <div>
        <div className="voice-name" title={entry.display_name}>
          {entry.display_name}
        </div>
        {entry.username ? <div className="voice-handle">{entry.username}</div> : null}
      </div>

      <div className="voice-figure">
        {entry.hidden ? (
          <span className="muted" style={{ fontSize: "1rem" }}>
            Hidden
          </span>
        ) : metric === "share" ? (
          `${((entry.share ?? 0) * 100).toFixed(2)}%`
        ) : (
          <>
            {formatAmount(entry.earned ?? "0")}
            <small>{symbol}</small>
          </>
        )}
      </div>

      <div className="voice-spark">
        <Sparkline values={entry.series} tone={direction} height={46} />
      </div>

      <div className="voice-tile-foot">
        <span>{entry.rewards} rewards</span>
        {entry.demo ? <span className="demo-chip">demo</span> : null}
      </div>
    </Link>
  );
}
