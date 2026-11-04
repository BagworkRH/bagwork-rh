"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import BrandLogo from "@/lib/brand";
import { getPlatformStats, type PlatformStats } from "@/lib/stats";
import { listCampaigns } from "@/services/campaigns";
import type { Campaign } from "@/types";

/** Compact form for a raw token amount: "1.2M", "8.4k", "912". */
function compact(value: string): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function budgetUsed(campaign: Campaign): number {
  const budget = Number(campaign.budget);
  const remaining = Number(campaign.remaining_budget);
  if (!Number.isFinite(budget) || budget <= 0 || !Number.isFinite(remaining)) return 0;
  return Math.max(0, Math.min(100, ((budget - remaining) / budget) * 100));
}

/**
 * Footer — live information rather than a link farm.
 *
 * A menu of dead links tells a visitor nothing. This shows what the platform is
 * actually doing right now: real headline figures and a bar per live campaign
 * for how much of its budget has been paid out. When the API is unreachable it
 * says so instead of inventing numbers.
 */
export default function Footer() {
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getPlatformStats(), listCampaigns().catch(() => [] as Campaign[])]).then(
      ([nextStats, nextCampaigns]) => {
        if (cancelled) return;
        setStats(nextStats);
        setCampaigns(nextCampaigns);
        setLoaded(true);
      }
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const live = campaigns.filter((c) => c.status === "ACTIVE").slice(0, 8);

  const metrics = stats
    ? [
        { label: "Rewards paid", value: compact(stats.rewards_paid_total) },
        { label: "Claims settled", value: stats.claims_completed.toLocaleString("en-US") },
        { label: "Active creators", value: stats.active_sellers.toLocaleString("en-US") },
        { label: "Campaigns live", value: stats.campaigns_live.toLocaleString("en-US") },
      ]
    : [];

  return (
    <footer className="site-footer">
      <div className="container">
        <div className="footer-live">
          <div>
            <div className="footer-live-head">
              <span className="live-dot" /> Live platform data
            </div>
            {!loaded ? (
              <div className="footer-metrics" aria-hidden="true">
                {Array.from({ length: 4 }).map((_, index) => (
                  <div key={index}>
                    <div className="skeleton skeleton-line" style={{ width: 60, height: 22 }} />
                    <div className="skeleton skeleton-line" style={{ width: 90, marginTop: 6 }} />
                  </div>
                ))}
              </div>
            ) : metrics.length === 0 ? (
              <p className="muted" style={{ fontSize: "0.85rem" }}>
                Live figures are unavailable right now — the API did not answer. Nothing is
                estimated in its place.
              </p>
            ) : (
              <div className="footer-metrics">
                {metrics.map((metric) => (
                  <div key={metric.label}>
                    <div className="v">{metric.value}</div>
                    <div className="k">{metric.label}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <div className="footer-live-head">Budget paid out · live campaigns</div>
            {live.length === 0 ? (
              <p className="muted" style={{ fontSize: "0.85rem" }}>
                No campaign is live at the moment.
              </p>
            ) : (
              <div className="footer-mini-bars">
                {live.map((campaign) => {
                  const used = budgetUsed(campaign);
                  return (
                    <div className="col" key={campaign.id} title={`${campaign.name}: ${Math.round(used)}% paid out`}>
                      <div className="bar" style={{ height: `${Math.max(4, used)}%` }} />
                      <span className="cap">{campaign.name}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <div className="footer-bottom">
          <Link href="/" className="brand" aria-label="bagworkRH home">
            <BrandLogo size={24} />
          </Link>
          <nav className="footer-links" aria-label="Footer">
            <Link href="/leaderboard">Leaderboard</Link>
            <Link href="/campaigns">Campaigns</Link>
            <Link href="/brand">For brands</Link>
            <Link href="/help">Help</Link>
            <Link href="/terms">Terms</Link>
            <Link href="/privacy">Privacy</Link>
          </nav>
          <span className="muted" style={{ fontSize: "0.78rem" }}>
            © {new Date().getFullYear()} bagworkRH. Rewards carry risk; nothing here is
            financial advice.
          </span>
        </div>
      </div>
    </footer>
  );
}
