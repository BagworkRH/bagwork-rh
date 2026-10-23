"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { getOverview } from "@/services/admin";
import type { OpsOverview } from "@/types/ops";

/** Platform overview: the figures a staff member needs before doing anything. */
export default function OpsOverviewPage() {
  const [data, setData] = useState<OpsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await getOverview());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the overview.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <p className="muted">Loading overview…</p>;
  if (error) return <div className="banner banner-error">{error}</div>;
  if (!data) return null;

  return (
    <>
      <div className="ops-stats">
        <Stat
          k="Sellers"
          v={data.sellers.total}
          sub={`${data.sellers.active} active · ${data.sellers.suspended} suspended`}
        />
        <Stat k="New sellers 24h" v={data.sellers.new_last_24h} />
        <Stat
          k="Campaigns"
          v={data.campaigns.total}
          sub={`${data.campaigns.active} active · ${data.campaigns.paused} paused`}
        />
        <Stat k="Posts tracked" v={data.posts.total} sub={`${data.posts.verified} verified`} />
        <Stat k="Rewards to review" v={data.rewards.pending_review} />
        <Stat k="Rewards claimable" v={data.rewards.available} />
        <Stat
          k="Risk flags open"
          v={data.risk.open}
          sub={`${data.risk.high} high · ${data.risk.medium} medium`}
        />
        <Stat
          k="Claims confirmed"
          v={data.claims.confirmed}
          sub={`${data.claims.open} open · ${data.claims.failed} failed`}
        />
      </div>

      <div className="grid">
        <div className="card">
          <h3>Money in flight</h3>
          <dl className="stats-list">
            <div>
              <dt>Campaign budget</dt>
              <dd>{data.campaigns.budget}</dd>
            </div>
            <div>
              <dt>Remaining</dt>
              <dd>{data.campaigns.remaining_budget}</dd>
            </div>
            <div>
              <dt>Rewards total</dt>
              <dd>{data.rewards.total_amount}</dd>
            </div>
          </dl>
          <p className="muted">
            Token units summed across every campaign, not a fiat value. Confirmed on-chain
            balances live in the treasury and escrow wallets.
          </p>
        </div>

        <div className="card">
          <h3>Queues that need a person</h3>
          <ul className="joined-campaigns">
            <QueueRow
              label="Rewards pending review"
              count={data.rewards.pending_review}
              href="/ops/rewards"
            />
            <QueueRow label="Risk flags open" count={data.risk.open} href="/ops/risk" />
            <QueueRow
              label="Posts awaiting metrics"
              count={data.posts.awaiting_metrics}
              href="/ops/posts"
            />
            <QueueRow
              label="Posts flagged suspicious"
              count={data.posts.flagged}
              href="/ops/posts"
            />
            <QueueRow label="Claims open" count={data.claims.open} href="/ops/claims" />
            <QueueRow
              label="Claims failed"
              count={data.claims.failed}
              href="/ops/claims"
            />
          </ul>
          <p className="muted">
            Audit events in the last 24 hours: {data.audit_events_last_24h}.
          </p>
        </div>
      </div>

      <p className="muted" style={{ marginTop: 16 }}>
        Generated {new Date(data.generated_at).toLocaleString()}. Risk review threshold:{" "}
        {data.risk.threshold}.
      </p>
    </>
  );
}

function Stat({ k, v, sub }: { k: string; v: number; sub?: string }) {
  return (
    <div className="ops-stat">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
      {sub ? <div className="muted" style={{ fontSize: "0.75rem" }}>{sub}</div> : null}
    </div>
  );
}

function QueueRow({ label, count, href }: { label: string; count: number; href: string }) {
  return (
    <li className="row" style={{ justifyContent: "space-between" }}>
      <span>
        {label} <span className="badge">{count}</span>
      </span>
      <Link href={href} className="btn btn-outline btn-sm">
        Open
      </Link>
    </li>
  );
}
