"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { formatAmount } from "@/lib/money";
import type { Campaign } from "@/types";

function committed(campaign: Campaign): number {
  const budget = Number(campaign.budget);
  const remaining = Number(campaign.remaining_budget);
  if (!Number.isFinite(budget) || !Number.isFinite(remaining)) return 0;
  return Math.max(0, budget - remaining);
}

function endLabel(value: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

/**
 * The same money, grouped two other ways: by campaign and by brand.
 *
 * Both are derived from the campaign list the server already sent, so switching
 * between them costs no request and shows no spinner.
 */
export default function SectorTables({ campaigns }: { campaigns: Campaign[] }) {
  const [tab, setTab] = useState<"campaigns" | "brands">("campaigns");

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

  return (
    <div className="card">
      <div className="board-head">
        <div className="board-title">
          <h2>By campaign &amp; brand</h2>
          <span className="muted" style={{ fontSize: "0.82rem" }}>
            where the money is committed
          </span>
        </div>
        <div className="seg" role="tablist" aria-label="Grouping">
          <button role="tab" aria-selected={tab === "campaigns"} className={tab === "campaigns" ? "is-active" : ""} onClick={() => setTab("campaigns")}>
            Campaigns
          </button>
          <button role="tab" aria-selected={tab === "brands"} className={tab === "brands" ? "is-active" : ""} onClick={() => setTab("brands")}>
            Brands
          </button>
        </div>
      </div>

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
        verified posts, including payouts still awaiting review.
      </p>
    </div>
  );
}
