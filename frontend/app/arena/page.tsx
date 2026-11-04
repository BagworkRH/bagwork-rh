"use client";

import { useEffect, useState } from "react";

import DeltaChip from "@/components/DeltaChip";
import RankedTile from "@/components/RankedTile";
import { formatAmount } from "@/lib/money";
import { getLeaderboard } from "@/services/leaderboard";
import type { Leaderboard } from "@/types";

/** Rank bands, the way a leaderboard is actually read: who is winning, then the chase. */
const RANGES = [
  { label: "Top 20", limit: 20, offset: 0 },
  { label: "21–50", limit: 30, offset: 20 },
  { label: "51–100", limit: 50, offset: 50 },
];

export default function ArenaPage() {
  const [board, setBoard] = useState<Leaderboard | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [range, setRange] = useState(RANGES[0]);

  useEffect(() => {
    setState("loading");
    getLeaderboard({ limit: range.limit, offset: range.offset })
      .then((data) => {
        setBoard(data);
        setState("ready");
      })
      .catch(() => setState("error"));
  }, [range]);

  const campaign = board?.campaign ?? null;
  const symbol = campaign?.token_symbol ?? "";
  const entries = board?.entries ?? [];
  const gainers = [...entries]
    .filter((entry) => !entry.hidden)
    .sort((a, b) => Number(b.delta_7d ?? 0) - Number(a.delta_7d ?? 0))
    .slice(0, 8);

  return (
    <div className="container section">
      <header className="arena-head">
        <div>
          <p className="eyebrow">Arena</p>
          <h1>{campaign ? campaign.name : "Top creators"}</h1>
          <p className="muted">
            What creators actually earned. Only settled rewards appear, and anyone who
            hides their earnings keeps their place without the figure.
          </p>
        </div>
        {campaign && (
          <div className="arena-totals">
            <div className="stat-box">
              <div className="num">
                {formatAmount(board?.totals.paid ?? "0")} <small>{symbol}</small>
              </div>
              <div className="muted">Paid out</div>
            </div>
            <div className="stat-box">
              <div className="num">{board?.totals.creators ?? 0}</div>
              <div className="muted">Creators paid</div>
            </div>
            <div className="stat-box">
              <div className="num">{board?.totals.rewards ?? 0}</div>
              <div className="muted">Rewards</div>
            </div>
          </div>
        )}
      </header>

      {board?.has_demo && (
        <div className="banner banner-note">
          Some entries here are <strong>labelled demonstration data</strong> —
          seeded to show how the arena looks, not real payouts. Everything else
          is money that actually moved.
        </div>
      )}

      {state === "loading" && <p className="muted">Loading the board…</p>}
      {state === "error" && (
        <div className="banner banner-error">
          Could not load the board. Refresh to try again.
        </div>
      )}

      {state === "ready" && entries.length === 0 && (
        <div className="card">
          <h3>No one has been paid yet</h3>
          <p className="muted">
            This board fills the moment a creator&apos;s reward is settled. Nothing here
            is estimated or projected - every figure is money that has actually moved.
          </p>
        </div>
      )}

      {state === "ready" && entries.length > 0 && (
        <>
          <nav className="range-tabs" aria-label="Rank range">
            {RANGES.map((option) => (
              <button
                key={option.label}
                className={`range-tab ${option.label === range.label ? "is-active" : ""}`}
                onClick={() => setRange(option)}
                aria-current={option.label === range.label}
              >
                {option.label}
              </button>
            ))}
          </nav>

          <div className="arena-layout">
            <div className="arena-tiles">
              {entries.map((entry) => (
                <RankedTile key={entry.rank} entry={entry} symbol={symbol} />
              ))}
            </div>

            <aside className="card arena-rail">
              <h3>Top earners this week</h3>
              {gainers.length === 0 ? (
                <p className="muted">No movement in the last seven days.</p>
              ) : (
                <table className="table-compact">
                  <thead>
                    <tr>
                      <th>Creator</th>
                      <th>Earned</th>
                      <th>7d</th>
                      <th>30d</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gainers.map((entry) => (
                      <tr key={entry.rank}>
                        <td data-label="Creator">
                          <span className="muted">#{entry.rank}</span> {entry.display_name}
                        </td>
                        <td data-label="Earned" className="money">
                          {formatAmount(entry.earned ?? "0")}
                        </td>
                        <td data-label="7d">
                          <DeltaChip value={entry.delta_7d} symbol={symbol} />
                        </td>
                        <td data-label="30d">
                          <DeltaChip value={entry.delta_30d} symbol={symbol} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
