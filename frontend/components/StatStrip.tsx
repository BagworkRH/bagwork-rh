"use client";

import { useState } from "react";

import TopGainersRail from "@/components/TopGainersRail";
import type { LeaderboardEntry } from "@/types";

type StatCard = {
  label: string;
  value: string;
  icon: React.ComponentType<{ size?: number }>;
};

/**
 * Platform headline stats with a toggle to swap in the Top Gainer rail.
 *
 * Kept as a client component so the show/stats toggle can use state without
 * pulling the whole async landing page into the client boundary.
 */
export default function StatStrip({
  cards,
  entries,
}: {
  cards: StatCard[];
  entries: LeaderboardEntry[];
}) {
  const [showTopGainers, setShowTopGainers] = useState(false);

  return (
    <section className="stat-strip">
      <div
        className="row"
        style={{
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 10,
          gridColumn: "1 / -1",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "0.9375rem" }}>Platform stats</h2>
        <button
          className="btn btn-outline btn-sm"
          onClick={() => setShowTopGainers((prev) => !prev)}
          style={{ height: 28, padding: "0 10px", fontSize: "0.78rem" }}
        >
          {showTopGainers ? "Show stats" : "Top gainers"}
        </button>
      </div>
      {showTopGainers ? (
        <TopGainersRail entries={entries} />
      ) : cards.length > 0 ? (
        cards.map((card) => {
          const Icon = card.icon;
          return (
            <div
              className="stat-box"
              key={card.label}
              style={{ display: "flex", alignItems: "center", gap: 12 }}
            >
              <span className="stat-icon">
                <Icon size={18} />
              </span>
              <div>
                <div className="num">{card.value}</div>
                <div className="muted">{card.label}</div>
              </div>
            </div>
          );
        })
      ) : null}
    </section>
  );
}
