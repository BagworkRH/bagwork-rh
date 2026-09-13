import Link from "next/link";
import { notFound } from "next/navigation";
import { apiRequest } from "@/lib/api";
import type { Campaign } from "@/types";

async function getCampaign(slug: string): Promise<Campaign | null> {
  try {
    return await apiRequest<Campaign>(`/api/v1/campaigns/${slug}/`);
  } catch {
    return null;
  }
}

export default async function CampaignDetailPage({
  params,
}: {
  params: { slug: string };
}) {
  const campaign = await getCampaign(params.slug);
  if (!campaign) notFound();

  return (
    <div className="container section">
      <Link href="/campaigns" className="muted">
        ← All campaigns
      </Link>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="campaign-card-top">
          <span className="badge badge-token">{campaign.token_symbol}</span>
          <span className="badge badge-ok">{campaign.status}</span>
        </div>
        <h1>{campaign.name}</h1>
        <p className="muted">{campaign.project_name}</p>
        <p>{campaign.description}</p>

        <dl className="stats-list">
          <div>
            <dt>Budget</dt>
            <dd>
              {campaign.budget} {campaign.token_symbol}
            </dd>
          </div>
          <div>
            <dt>Remaining</dt>
            <dd>
              {campaign.remaining_budget} {campaign.token_symbol}
            </dd>
          </div>
          <div>
            <dt>Reward model</dt>
            <dd>{campaign.reward_model}</dd>
          </div>
          <div>
            <dt>Rate</dt>
            <dd>
              {campaign.reward_rate} {campaign.token_symbol}
            </dd>
          </div>
          <div>
            <dt>Max / seller</dt>
            <dd>{campaign.maximum_reward_per_seller}</dd>
          </div>
          <div>
            <dt>Chain</dt>
            <dd>{campaign.chain_id}</dd>
          </div>
        </dl>

        <h3>Reward rules</h3>
        <ul>
          <li>Model: {campaign.reward_model}</li>
          <li>Rate: {campaign.reward_rate} per unit</li>
          {Object.entries(campaign.requirements_json ?? {}).map(([key, value]) => (
            <li key={key}>
              {key}: {String(value)}
            </li>
          ))}
        </ul>

        <div className="row">
          <Link href="/dashboard" className="btn btn-primary">
            Join campaign
          </Link>
        </div>
        <p className="muted" style={{ marginTop: 12 }}>
          Rules and anti-fraud measures apply. Posts are verified before any
          reward is calculated.
        </p>
      </div>
    </div>
  );
}