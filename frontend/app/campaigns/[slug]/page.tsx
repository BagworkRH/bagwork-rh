import Link from "next/link";
import { notFound } from "next/navigation";

import { ArrowRightIcon, CheckIcon, ClockIcon, ShieldIcon, TargetIcon } from "@/components/icons";
import JoinCampaignButton from "@/components/JoinCampaignButton";
import { ProgressBar } from "@/components/ui";
import { apiRequest } from "@/lib/api";
import { formatAmount } from "@/lib/money";
import type { Campaign } from "@/types";

async function getCampaign(slug: string): Promise<Campaign | null> {
  try {
    return await apiRequest<Campaign>(`/api/v1/campaigns/${slug}/`);
  } catch {
    return null;
  }
}

function dateLabel(value: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function statusClass(status: Campaign["status"]): string {
  if (status === "ACTIVE") return "badge badge-ok";
  if (status === "PAUSED") return "badge badge-warn";
  return "badge badge-muted";
}

export default async function CampaignDetailPage({ params }: { params: { slug: string } }) {
  const campaign = await getCampaign(params.slug);
  if (!campaign) notFound();

  const budget = Number(campaign.budget);
  const remaining = Number(campaign.remaining_budget);
  const spent = Number.isFinite(budget) && Number.isFinite(remaining) ? Math.max(0, budget - remaining) : 0;
  const usedPct = budget > 0 ? (spent / budget) * 100 : 0;
  const rate = Number(campaign.reward_rate);
  const capacity = rate > 0 ? Math.floor(budget / rate) : 0;
  const settled = rate > 0 ? Math.floor(spent / rate) : 0;
  const requirements = Object.entries(campaign.requirements_json ?? {});

  return (
    <div className="stack" style={{ gap: 20 }}>
      <Link href="/campaigns" className="muted" style={{ fontSize: "0.875rem" }}>
        ← All campaigns
      </Link>

      <div className="page-head">
        <div>
          <span className="eyebrow">
            <TargetIcon size={12} /> {campaign.project_name}
          </span>
          <h1>{campaign.name}</h1>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            <span className={statusClass(campaign.status)}>{campaign.status}</span>
            <span className="badge badge-token badge-plain">{campaign.token_symbol}</span>
            <span className="chip badge-plain">
              <ClockIcon size={13} /> Ends {dateLabel(campaign.end_at)}
            </span>
          </div>
        </div>
        <div className="actions" style={{ marginTop: 0 }}>
          <JoinCampaignButton campaignId={campaign.id} initiallyJoined={campaign.joined} />
        </div>
      </div>

      <div className="split">
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <h2>Overview</h2>
            <p style={{ color: "var(--text-2)" }}>{campaign.description}</p>
            <dl className="stats-list">
              <div>
                <dt>Reward per post</dt>
                <dd>
                  {formatAmount(campaign.reward_rate)} {campaign.token_symbol}
                </dd>
              </div>
              <div>
                <dt>Max per creator</dt>
                <dd>{formatAmount(campaign.maximum_reward_per_seller)}</dd>
              </div>
              <div>
                <dt>Max rewards</dt>
                <dd>{campaign.maximum_rewards_per_seller}</dd>
              </div>
              <div>
                <dt>Starts</dt>
                <dd style={{ fontFamily: "var(--font-sans)" }}>{dateLabel(campaign.start_at)}</dd>
              </div>
              <div>
                <dt>Ends</dt>
                <dd style={{ fontFamily: "var(--font-sans)" }}>{dateLabel(campaign.end_at)}</dd>
              </div>
              <div>
                <dt>Chain</dt>
                <dd>{campaign.chain_id}</dd>
              </div>
            </dl>
          </div>

          <div className="card">
            <h2>Requirements</h2>
            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
              <li style={{ display: "flex", gap: 10, marginBottom: 10 }}>
                <CheckIcon size={18} className="money" />
                <span>
                  Publish an <strong>original</strong> post — reposts and quotes of
                  someone else&apos;s post are not payable.
                </span>
              </li>
              <li style={{ display: "flex", gap: 10, marginBottom: 10 }}>
                <CheckIcon size={18} className="money" />
                <span>
                  Reward is{" "}
                  <strong>
                    {formatAmount(campaign.reward_rate)} {campaign.token_symbol}
                  </strong>{" "}
                  per verified post.
                </span>
              </li>
              {requirements.map(([key, value]) => (
                <li key={key} style={{ display: "flex", gap: 10, marginBottom: 10 }}>
                  <CheckIcon size={18} className="money" />
                  <span>
                    <strong>{key.replace(/_/g, " ")}:</strong> {String(value)}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <div className="card">
            <h2>How to take part</h2>
            <ol style={{ margin: 0, paddingLeft: 20, color: "var(--text-2)" }}>
              <li style={{ marginBottom: 8 }}>
                Join the campaign, then connect the social account you publish from.
              </li>
              <li style={{ marginBottom: 8 }}>
                Publish an original post that meets the requirements above.
              </li>
              <li style={{ marginBottom: 8 }}>
                We discover the post, verify it and calculate the reward automatically.
              </li>
              <li>Claim your reward from the Wallet page once it is available.</li>
            </ol>
          </div>
        </div>

        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <div className="card-head">
              <h3>Budget</h3>
              <span className="muted" style={{ fontSize: "0.8125rem" }}>
                {Math.round(usedPct)}% used
              </span>
            </div>
            <div className="stat-value" style={{ fontSize: "1.5rem" }}>
              {formatAmount(campaign.remaining_budget)} <small>{campaign.token_symbol} left</small>
            </div>
            <div style={{ margin: "12px 0 8px" }}>
              <ProgressBar value={usedPct} tone={usedPct >= 90 ? "warn" : "brand"} label="Budget used" />
            </div>
            <p className="muted" style={{ fontSize: "0.8125rem" }}>
              {settled} of {capacity} payouts settled from a {formatAmount(campaign.budget)}{" "}
              {campaign.token_symbol} budget.
            </p>
          </div>

          <div className="card">
            <div className="card-head">
              <h3>Rules &amp; safety</h3>
              <ShieldIcon size={18} />
            </div>
            <p className="muted" style={{ fontSize: "0.875rem" }}>
              Posts are verified before any reward is calculated. Reposts, duplicates and
              posts outside the campaign window are refused. Payout is bounded per account,
              and suspicious activity goes to a human review queue.
            </p>
            <Link href="/help" className="btn btn-outline btn-sm">
              How verification works <ArrowRightIcon size={14} />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
